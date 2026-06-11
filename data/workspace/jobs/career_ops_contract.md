# Jobs Career-Ops Contract

## Objetivo

`/jobs` funciona como filtro operativo de oportunidades laborales. Evalua primero, registra despues y postula solo con autorizacion explicita de Mauro.

## Estados canonicos

- `evaluated`: oferta evaluada, pendiente decision.
- `applied`: postulacion enviada.
- `responded`: empresa respondio, aun sin entrevista.
- `interview`: proceso de entrevista activo.
- `offer`: oferta recibida.
- `rejected`: rechazo recibido.
- `discarded`: descartada por Mauro o cerrada.
- `skip`: no conviene aplicar.

## Recomendaciones

- `apply`: fit alto; sugerir `/jobs postular N` si viene desde matches.
- `monitor`: fit medio o faltan datos; revisar en 3 dias.
- `skip`: fit bajo, riesgo alto o duplicada.

## Archivos

- Tracker: `data/workspace/jobs/applications.csv`
- Reportes: `data/workspace/jobs/reports/`
- Ultimos matches: `data/workspace/jobs/last_matches.json`
- CV indexado: `data/workspace/jobs/cv_index.json`

## Regla humana

La IA puede evaluar y recomendar. La IA no debe enviar postulaciones salvo instruccion explicita.
