# OpenClaw Repo Hygiene

This repo mixes code, OpenClaw workspaces and local runtime data. Keep the
boundary explicit so another agent can work safely.

## Commit

- Code and reusable scripts: `scripts/`, `config/`, `data/config/extensions/`.
- Agent instructions: `AGENTS.md`, `SOUL.md`, checked-in workspace docs.
- Sanitized examples and operational docs.

## Do not commit

- `data/workspace/**/data/*_state.json`
- `data/workspace/**/memory/`
- `data/workspace/*/DREAMS.md`
- `config/whatsapp_users.json`
- OAuth tokens, browser storage state, logs, media, SQLite DBs.
- Scratch scripts named `check_*.py`, `test_*.py`, `run_*.py` or `*_fix.py` under `data/workspace/`.

## Scratch work

Use `/tmp/openclaw-<topic>-<date>` for one-off experiments. If the experiment
becomes durable, move it to `scripts/`, add a focused test, and document the
command in the relevant workspace `AGENTS.md`.

## End-of-turn checklist

```bash
git status --short
python3 -m py_compile scripts/<changed>.py
node --check data/config/extensions/channel-delegate-hook/index.js
```

Only stage files that belong to the current task.
