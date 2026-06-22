# Secretos locales

La ubicacion canonica es `runtime/secrets/`. El enlace `secrets` se conserva para
compatibilidad con scripts existentes. Ningun archivo real se sube a GitHub.

## Archivos esperados

| Archivo | Uso |
|---|---|
| `gmail_credentials.json` | OAuth Gmail para finanzas y boletas |
| `google_workspace_token.json` | **Token canonico** Gmail + Calendar + Sheets + Drive |
| `gmail_token.json` | Alias legacy (readonly); se sincroniza desde workspace |
| `gmail_modify_token.json` | Alias legacy (modify); se sincroniza desde workspace |
| `github_hl_miko_credentials` | Credenciales Git para HL-Go |
| `github_hl_miko_pat` | PAT alternativo de HL-Go |
| `hl_go.env` | Variables locales de HL-Go |
| `linkedin_innovacionradical.env` | Login LinkedIn de Intel |
| `linkedin_innovacionradical_storage_state.json` | Sesion LinkedIn de Intel |
| `linkedin_storage_state.json` | Sesion LinkedIn personal de Jobs |
| `laborum_storage_state.json` | Sesion Laborum |
| `chiletrabajos_storage_state.json` | Sesion ChileTrabajos |
| `whatsapp_allow_from.txt` | Numeros permitidos de WhatsApp |
| `.env` | Credenciales de portales Jobs |

Permisos esperados:

```bash
chmod 700 runtime/secrets
find runtime/secrets -type f -exec chmod 600 {} +
```

La configuracion del gateway permanece en `data/config/openclaw.json`. La
configuracion del stack se genera desde `config/stack.env.example` hacia
`openclaw/.env`.

## Gmail OAuth (renovar y evitar perdida)

**Fuente canonica:** `google_workspace_token.json`. Los archivos `gmail_token.json`
y `gmail_modify_token.json` son aliases legacy que `scripts/gmail_oauth_common.py`
sincroniza automaticamente cuando el workspace token sigue valido.

### Reautorizar (cuando falle el refresh)

```bash
cd /home/mauro/Dev/openclaw-mauro
.venv-finanzas/bin/python scripts/google_workspace_oauth.py auth-url
# Abrir auth_url en navegador, autorizar, copiar URL localhost final:
.venv-finanzas/bin/python scripts/google_workspace_oauth.py exchange --callback-url 'http://localhost:44567/?code=...&state=...'
.venv-finanzas/bin/python scripts/google_workspace_oauth.py check
```

El `exchange` propaga el refresh token a los aliases legacy automaticamente.

### Salud automatica

Cron cada 6h: `scripts/run-gmail-oauth-health.sh`

- Valida los 3 tokens Gmail
- Re-sincroniza legacy si el workspace sigue OK
- Alerta por WhatsApp si todo falla (cooldown 12h)

Manual:

```bash
.venv-finanzas/bin/python scripts/gmail_oauth_health.py --json
.venv-finanzas/bin/python scripts/gmail_oauth_common.py  # via health/check
```

### Evitar que expire de nuevo

1. **Google Cloud Console** → APIs & Services → OAuth consent screen → publicar la app en **Production** (en Testing los refresh tokens expiran a los 7 dias).
2. Usar siempre `google_workspace_oauth.py` para reautorizar; no crear grants separados con `gmail_modify_oauth.py` salvo emergencia.
3. No revocar acceso manualmente en https://myaccount.google.com/permissions
4. El health cron detecta caidas antes de que acumulen miles de errores en logs.
