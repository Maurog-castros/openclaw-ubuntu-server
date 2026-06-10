# Intel + LinkedIn (Innovación Radical)

Scout **solo lectura** para el agente Intel: feed, búsqueda por keywords y borradores sugeridos (publicación manual).

## Cuenta

- Página: [Innovación Radical en LinkedIn](https://www.linkedin.com/company/innovaci%C3%B3nradical/)
- Web: https://innovacionradical.cl/
- Sesión: `secrets/linkedin_innovacionradical_storage_state.json` (cookies Playwright)

## Instalación (servidor)

```bash
cd /home/mauro/openclaw-mauro
python3 -m venv .venv-linkedin-intel
.venv-linkedin-intel/bin/pip install -r scripts/requirements-linkedin-agent.txt
.venv-linkedin-intel/bin/playwright install chromium
cp secrets/linkedin_intel.env.example secrets/linkedin_innovacionradical.env
# Editar .env con email (opcional, solo login inicial)
chmod 600 secrets/linkedin_innovacionradical.env
```

## Login inicial (una vez)

En servidor con pantalla o `xvfb-run`:

```bash
xvfb-run -a .venv-linkedin-intel/bin/python scripts/linkedin_intel_scout.py login --headed
```

Si LinkedIn pide captcha/2FA, completa manualmente en el navegador virtual.

## Scan diario

```bash
.venv-linkedin-intel/bin/python scripts/linkedin_intel_scout.py scan --json
```

Salidas:

| Archivo | Contenido |
|---------|-----------|
| `data/workspace/marketing/intel/data/linkedin_signals_YYYY-MM-DD.json` | Señales raw |
| `data/workspace/marketing/intel/reports/YYYY-MM-DD-linkedin-intel.md` | Reporte Intel |
| `data/workspace/marketing/content/drafts/linkedin/YYYY-MM-DD-linkedin-drafts.md` | Borradores sugeridos |

## Keywords (config)

Editar `config/linkedin_intel/config.json`: devops, sre, agentes ia, mlops, llm, rag, etc.

Competidores: añadir URLs en `"competitors": ["https://www.linkedin.com/company/..."]`.

## Agente Intel

En WhatsApp o chat:

```text
/intel linkedin scan
/intel tendencias linkedin devops
```

Intel debe ejecutar `linkedin_intel_scout.py scan --json` y resumir top señales + borradores.

## Reglas

- **No publicar** automáticamente en LinkedIn.
- Pausas entre búsquedas (config `pause_between_searches_sec`).
- Cuenta separada del agente de jobs (`linkedin_storage_state.json`).
