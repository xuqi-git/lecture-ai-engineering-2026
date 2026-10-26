"""Small official DeepSeek Chat Completions adapter; no new dependencies.

Only https://api.deepseek.com is used. No automatic retries or tool calls.
Docs checked 2026-10-26: https://api-docs.deepseek.com/api/create-chat-completion/
"""

import json
from types import SimpleNamespace as NS
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class DeepSeekAPIError(RuntimeError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


class DeepSeekClient:
    """Expose the small interface used by benchmark.measure_once."""

    def __init__(self, api_key, *, timeout=90, opener=urlopen):
        self._credential = api_key
        self._timeout = timeout
        self._opener = opener
        self.models = self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def _request(self, path, payload=None):
        body = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
        request = Request("https://api.deepseek.com" + path, data=body,
                          headers={"Authorization": "Bearer " + self._credential,
                                   "Content-Type": "application/json"},
                          method="POST" if body is not None else "GET")
        try:
            with self._opener(request, timeout=self._timeout) as response:
                return json.load(response)
        except HTTPError as exc:
            # Request headers (including credentials) are never recorded.
            try:
                message = json.loads(exc.read().decode()).get("error", {}).get("message", "API request failed")
            except (ValueError, AttributeError):
                message = "API request failed"
            message = str(message).replace(self._credential, "[REDACTED]")
            raise DeepSeekAPIError(exc.code, message) from None

    def list(self):
        return [NS(name=item["id"], supported_actions=["generateContent"])
                for item in self._request("/models")["data"]]

    def generate_content(self, *, model, contents, config):
        data = self._request("/chat/completions", {
            "model": model,
            "messages": ([{"role": "user", "content": contents}] if isinstance(contents, str) else
                         [{"role": "assistant" if m["role"] == "model" else m["role"],
                           "content": "".join(part["text"] for part in m["parts"])} for m in contents]),
            "max_tokens": config.max_output_tokens,
            "stream": False,
            # Both compared models use the same explicitly non-thinking mode.
            "thinking": {"type": "disabled"},
        })
        choice = data["choices"][0]
        usage = data.get("usage") or {}
        details = usage.get("completion_tokens_details") or {}
        thoughts = details.get("reasoning_tokens")
        completion = usage.get("completion_tokens")
        # Preserve the API's completion count. With thinking disabled this is
        # visible output; never invent a missing reasoning count as zero.
        visible = (completion - thoughts if completion is not None and thoughts is not None
                   else completion)
        finish = choice.get("finish_reason")
        reason = {"stop": "STOP", "length": "MAX_TOKENS"}.get(finish, finish)
        return NS(text=choice["message"].get("content"), model_version=data.get("model"),
                  candidates=[NS(finish_reason=NS(value=reason))],
                  usage_metadata=NS(prompt_token_count=usage.get("prompt_tokens"),
                                    candidates_token_count=visible,
                                    thoughts_token_count=thoughts,
                                    cached_content_token_count=usage.get("prompt_cache_hit_tokens"),
                                    total_token_count=usage.get("total_tokens")))
