#!/usr/bin/env python3
from pathlib import Path

path = Path("/home/mauro/openclaw-mauro/scripts/gmail_organize_agent.py")
text = path.read_text(encoding="utf-8")

if "resolve_modify_token" not in text:
    insert = "from vida_common import secret_path, writable_secret_path\n\n\n"
    text = text.replace("from googleapiclient.errors import HttpError\n\n", "from googleapiclient.errors import HttpError\n\n" + insert)
    helper = '''
def resolve_modify_token(token_arg: str) -> Path:
    if token_arg != "secrets/gmail_modify_token.json":
        return ROOT / token_arg
    found = secret_path("gmail_modify_token.json")
    return found if found else writable_secret_path("gmail_modify_token.json")


'''
    text = text.replace("def gmail_service(token_file: Path):", helper + "def gmail_service(token_file: Path):")

old = "    try:\n        if args.cmd == \"scan\":\n            result = cmd_scan(args)"
new = "    args.token = str(resolve_modify_token(args.token))\n\n    try:\n        if args.cmd == \"scan\":\n            result = cmd_scan(args)"
if old not in text:
    raise SystemExit("main block not found")
text = text.replace(old, new)

# Broader inbox cleanup default
text = text.replace(
    'scan.add_argument("--query", default="is:unread newer_than:90d")',
    'scan.add_argument("--query", default="in:inbox newer_than:365d")',
)
text = text.replace(
    "scan.add_argument(\"--max-results\", type=int, default=100)",
    "scan.add_argument(\"--max-results\", type=int, default=300)",
)

path.write_text(text, encoding="utf-8")
print("gmail_organize_agent patched")
