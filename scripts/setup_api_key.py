"""Run locally by the account owner. Input is hidden; secrets are never printed."""

import argparse
import getpass
import os
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=["deepseek", "gemini"], default="deepseek")
    args = parser.parse_args()
    variable = "DEEPSEEK_API_KEY" if args.provider == "deepseek" else "GEMINI_API_KEY"
    root = Path(__file__).resolve().parents[1]
    destination = root / ".env"
    if destination.exists():
        raise SystemExit(".env already exists; kept unchanged.")
    key = getpass.getpass(f"{args.provider} API key (hidden): ").strip()
    if not key or any(c in key for c in "\r\n\"' "):
        raise SystemExit("Invalid key; no file was written.")
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        handle.write(f"{variable}={key}\n")
    print("Saved locally to git-ignored .env with owner-only permissions. Key not displayed.")


if __name__ == "__main__":
    main()
