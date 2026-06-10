# Secretos locales (no versionados)

Esta carpeta **no se sube a GitHub**. Crea aquí tus archivos reales en el servidor o en tu máquina.

## Archivos esperados

| Archivo | Uso |
|---------|-----|
| `gmail_credentials.json` | OAuth Gmail (finanzas / boletas) |
| `gmail_token.json` | Token Gmail renovado |
| `github_hl_miko_credentials` | Credenciales git para HL-Go (`user:token`) |
| `github_hl_miko_pat` | PAT alternativo HL-Go |
| `hl_go.env` | Variables HL-Go (DB, URLs) |
| `linkedin_innovacionradical.env` | Login LinkedIn intel |
| `linkedin_innovacionradical_storage_state.json` | Sesión Playwright LinkedIn |
| `whatsapp_allow_from.txt` | Números permitidos WhatsApp (uno por línea) |

## OpenClaw stack

Copia `config/stack.env.example` a `openclaw/.env` y rellena tokens.

La config del gateway vive en `data/config/openclaw.json` (también ignorada por git). Aplícala con los scripts `scripts/apply_openclaw_*.py` después de clonar.
