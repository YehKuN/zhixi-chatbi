from __future__ import annotations

import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
TEMPLATE_PATH = ROOT / ".env.example"


def replace_line(text: str, key: str, value: str, *, fill_only_if_blank: bool = False) -> str:
    prefix = key + "="
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            if not fill_only_if_blank or not line[len(prefix) :].strip():
                lines[index] = prefix + value
            return "\n".join(lines) + "\n"
    lines.append(prefix + value)
    return "\n".join(lines) + "\n"


def main() -> int:
    if not ENV_PATH.exists():
        ENV_PATH.write_text(TEMPLATE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    text = ENV_PATH.read_text(encoding="utf-8")
    if not any(
        line.startswith("SECRET_MASTER_KEY=") and line.split("=", 1)[1].strip()
        for line in text.splitlines()
    ):
        text = replace_line(
            text, "SECRET_MASTER_KEY", secrets.token_urlsafe(48), fill_only_if_blank=True
        )
    text = replace_line(
        text, "CORS_ORIGINS", "http://127.0.0.1:5280,http://localhost:5280", fill_only_if_blank=True
    )
    text = replace_line(text, "VITE_API_BASE_URL", "http://127.0.0.1:8280", fill_only_if_blank=True)
    ENV_PATH.write_text(text, encoding="utf-8")
    print("local_env_ready=true")
    print(
        "deepseek_key_from_process_environment="
        + str(bool(os.environ.get("DEEPSEEK_API_KEY", "").strip())).lower()
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
