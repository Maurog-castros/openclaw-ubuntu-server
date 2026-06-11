# AGENTS.md

## Repo hygiene

- Work in `/home/mauro/Dev/openclaw-mauro` on the Ubuntu Server when changing production OpenClaw.
- Do not leave loose probe scripts in `data/workspace/`. Use `/tmp/openclaw-*` for experiments.
- Durable scripts belong in `scripts/` and must have a matching focused test when practical.
- Runtime user data stays out of git: profiles, state files, registries, dreams, credentials, media, logs and SQLite DBs.
- Personal config such as `config/whatsapp_users.json` stays local; commit only sanitized examples.
- Before finishing, run `git status --short` and either commit intentional code/docs or delete/ignore temporary files.
- Do not revert other agents' changes. If the tree is dirty, stage only the files you intentionally changed.

## Validation

- Python changes: run `python3 -m py_compile` on touched scripts and the focused test file.
- WhatsApp routing changes: test `scripts/channel_delegate.py --text ... --peer +56945046845 --json`.
- Gateway hook changes: run `node --check data/config/extensions/channel-delegate-hook/index.js` and restart only the affected container.
- Destructive cleanup: verify absolute paths stay inside this repo, then delete only explicit candidates.

## Commit discipline

- Commit on the Ubuntu Server repo only unless Mauro explicitly asks for the Windows checkout.
- Keep commits scoped by behavior: one feature/fix/cleanup per commit.
- Never commit secrets, real phone lists, OAuth tokens, browser session state, or generated user memories.
