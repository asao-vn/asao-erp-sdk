"""A stand-in for an agent CLI: answers with what it was given, from standard input or its last argument."""
import os
import sys

prompt = sys.argv[-1] if len(sys.argv) > 1 and sys.argv[1] == "--arg" else sys.stdin.read()
with open(os.environ["FAKE_AGENT_LOG"], "w", encoding="utf-8") as log:
    log.write(prompt)
if "FAIL" in os.environ.get("FAKE_AGENT_MODE", ""):
    sys.exit(3)
print(f"## Tóm tắt\nĐã đọc {len(prompt)} ký tự.")
