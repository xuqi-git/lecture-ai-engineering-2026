import io
import json
from types import SimpleNamespace as NS
from urllib.error import HTTPError

import pytest

from app.deepseek_api import DeepSeekClient, DeepSeekAPIError


def test_request_and_usage_mapping():
    requests = []
    def opener(request, timeout):
        requests.append((request, timeout))
        return io.BytesIO(json.dumps(dict(model="actual-model", choices=[dict(
            message=dict(content="回答"),finish_reason="stop")],usage=dict(
            prompt_tokens=20,completion_tokens=5,total_tokens=25,prompt_cache_hit_tokens=10))).encode())
    client = DeepSeekClient("offline-placeholder",opener=opener)
    result = client.generate_content(model="deepseek-flash",contents="質問",config=NS(max_output_tokens=2048))
    request,timeout = requests[0]
    assert request.full_url == "https://api.deepseek.com/chat/completions"
    body = json.loads(request.data)
    assert body["thinking"] == dict(type="disabled")
    assert body["max_tokens"] == 2048
    assert body["messages"] == [dict(role="user",content="質問")]
    assert "tools" not in body
    assert timeout == 90
    assert result.model_version == "actual-model"
    assert result.usage_metadata.candidates_token_count == 5
    assert result.usage_metadata.thoughts_token_count is None
    assert result.usage_metadata.cached_content_token_count == 10


def test_error_has_status_and_does_not_retry_or_leak_key():
    calls=[]
    def opener(request,timeout):
        calls.append(request)
        raise HTTPError(request.full_url,429,"Too many requests",{},
                        io.BytesIO(b'{"error":{"message":"offline-placeholder quota"}}'))
    client=DeepSeekClient("offline-placeholder",opener=opener)
    with pytest.raises(DeepSeekAPIError) as error:
        client.list()
    assert error.value.code == 429
    assert "offline-placeholder" not in str(error.value)
    assert len(calls) == 1


def test_list_models_uses_account_response():
    client=DeepSeekClient("offline-placeholder",opener=lambda request,timeout:
                          io.BytesIO(b'{"data":[{"id":"account-model"}]}'))
    assert client.list()[0].name == "account-model"


def test_completion_including_reasoning_is_not_double_counted():
    body=dict(model="a",choices=[dict(message=dict(content="result"),finish_reason="length")],
              usage=dict(prompt_tokens=10,completion_tokens=30,total_tokens=40,
                         completion_tokens_details=dict(reasoning_tokens=20)))
    client=DeepSeekClient("offline-placeholder",opener=lambda request,timeout:
                          io.BytesIO(json.dumps(body).encode()))
    result=client.generate_content(model="a",contents="q",config=NS(max_output_tokens=30))
    assert result.usage_metadata.candidates_token_count == 10
    assert result.usage_metadata.thoughts_token_count == 20
    assert result.usage_metadata.total_token_count == 40
    assert result.candidates[0].finish_reason.value == "MAX_TOKENS"

def test_history_converts_model_role_to_assistant():
    calls=[]
    def opener(request,timeout):
        calls.append(json.loads(request.data))
        return io.BytesIO(b'{"choices":[{"message":{"content":"ok"},"finish_reason":"stop"}],"usage":{}}')
    client=DeepSeekClient("offline-placeholder",opener=opener)
    history=[dict(role="user",parts=[dict(text="q1")]),dict(role="model",parts=[dict(text="a1")]),dict(role="user",parts=[dict(text="q2")])]
    client.generate_content(model="a",contents=history,config=NS(max_output_tokens=100))
    assert calls[0]["messages"]==[dict(role="user",content="q1"),dict(role="assistant",content="a1"),dict(role="user",content="q2")]
