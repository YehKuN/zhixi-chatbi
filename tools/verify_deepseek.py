from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    if not os.environ.get("DEEPSEEK_API_KEY", "").strip():
        print("DEEPSEEK_API_KEY is not present in this process; skipped external smoke request.")
        return 2
    request = urllib.request.Request(
        "http://127.0.0.1:8280/ai/deepseek/analyze",
        data=json.dumps(
            {
                "question": (
                    "请基于演示数据，用一句话指出 2026 年 10 月 1 日至 29 日营收"
                    "较 9 月同期的变化，并只给结论。"
                )
            },
            ensure_ascii=False,
        ).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    chunks = 0
    characters = 0
    final_state = ""
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            print(f"http_status={response.status}")
            for raw in response:
                line = raw.decode("utf-8", errors="replace").strip()
                if line.startswith("event:"):
                    final_state = line.removeprefix("event:").strip()
                elif line.startswith("data:"):
                    payload = json.loads(line.removeprefix("data:").strip())
                    if final_state == "delta":
                        delta = payload.get("text", "")
                        chunks += 1
                        characters += len(delta)
                    elif final_state == "error":
                        print("stream_error=" + str(payload.get("message", "unknown error")))
                        return 1
                    elif final_state == "done":
                        print("stream_done=true")
        if not chunks or not characters or final_state != "done":
            print(
                "stream_incomplete=true "
                f"chunks={chunks} characters={characters} "
                f"final_event={final_state}"
            )
            return 1
        print(f"stream_chunks={chunks} output_characters={characters} deepseek_responses_ok=true")
        return 0
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"http_status={exc.code}")
        print("response_body=" + body[:500])
        return 1
    except Exception as exc:
        print(f"smoke_test_failed={type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
