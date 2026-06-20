# Secretos locales

La ubicacion canonica es `runtime/secrets/`. El enlace `secrets` se conserva para
compatibilidad con scripts existentes. Ningun archivo real se sube a GitHub.

## Archivos esperados

| Archivo | Uso |
|---|---|
| `gmail_credentials.json` | OAuth Gmail para finanzas y boletas |
| `gmail_token.json` | Token Gmail renovable |
| `gmail_modify_token.json` | Token Gmail con scope `gmail.modify` |
| `google_workspace_token.json` | Gmail, Calendar, Drive y Sheets |
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
