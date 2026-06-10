# Agente `care` 🌿

**Prefijo:** `/care`  
**Modelo OpenClaw:** `openclaw/care`  
**Descripción:** Diario personal, salud, ánimo, medicamentos y rutina diaria.

## Qué hace

- **Diario** — actividades, ánimo, eventos (`data/diary/YYYY-MM-DD.md`)
- **Medicamentos** — consulta y recordatorios desde `data/medications.json`
- **Perfil** — onboarding psicológico gradual (`vida_profile.py`)
- **Inspiración** — frases cortas contextualizadas (`vida_inspire.py`)
- **Calendario** — citas próximas; fotos de órdenes de exámenes → OCR + evento Google Calendar
- **Despensa** — inventario y sugerencias de comida con lo disponible (`data/pantry.json`)
- **Check-ins** — ánimo y rutina (`vida_checkin.py`)

## Delegate obligatorio

```sh
/home/node/openclaw-mauro/scripts/run-vida-py.sh \
  /home/node/openclaw-mauro/scripts/vida_delegate.py --text "<mensaje>" --json
```

Con foto de orden médica: añadir `--has-media`. Copiar `whatsapp_reply` literal.

## Scripts

`vida_delegate.py`, `vida_diary.py`, `vida_meds.py`, `vida_pantry.py`, `vida_profile.py`, `vida_inspire.py`, `vida_calendar.py`, `vida_checkin.py`, `vida_exam_appointment.py`, `vida_exam_vision.py`, `vida_calendar_create.py`, `vida_calendar_oauth.py`

## Canales

- WhatsApp/Telegram con prefijo `/care` o enrutado automático
- **Alexa** — skill invocation name `care`

## Workspace

`/home/node/.openclaw/workspace/care`  
Detalle operativo: `care/AGENTS.md`, `care/SOUL.md`, `care/TOOLS.md`

## No es

No es un agente clínico/EMR ni triaje hospitalario. Es asistente de **vida diaria y bienestar personal** de Mauro.
