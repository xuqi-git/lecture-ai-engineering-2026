"""Run locally by the account owner. Input is hidden; secrets are never printed."""

import getpass
import os
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    destination = root / ".env"
    if destination.exists():
        raise SystemExit(".env already exists; kept unchanged.")
    key = getpass.getpass("Gemini API key (hidden): ").strip()
    if not key or any(c in key for c in "\r\n\"' "):
        raise SystemExit("Invalid key; no file was written.")
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        handle.write(f"GEMINI_API_KEY={key}\n")
    print("Saved locally to git-ignored .env with owner-only permissions. Key not displayed.")


if __name__ == "__main__":
    main()
