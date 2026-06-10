---
name: content-draft
description: "Genera drafts de contenido tecnico para Mauro (DevOps + IA aplicada): LinkedIn post/carrusel/articulo, X thread, ebook chapter, demo script. NO publica. Aplica filtros anti-hype. Trigger: 'draft post', 'crea carrusel', 'thread sobre', 'capitulo ebook', 'guion demo'."
---

# content-draft — Generador de drafts tecnicos

Skill de produccion de borradores. **Nunca publica.** Solo genera archivos markdown listos para revision humana.

## Argumentos

- `format` (requerido): `linkedin-post | linkedin-carousel | linkedin-article | x-thread | ebook-chapter | demo-script | outreach-msg`
- `topic` (requerido): tema corto
- `hook` (opcional): primera linea propuesta
- `source` (opcional): ruta a reporte Intel o nota referencia
- `audience` (opcional): default segun formato (LinkedIn=CTO/DevOps lead, X=tech senior, ebook=mid-senior tecnico)
- `length` (opcional): override default por formato

## Procedimiento

1. Leer template correspondiente desde `templates/<format>.md` si existe. Si no, usar estructura interna.
2. Si `source` apunta a reporte Intel: leerlo y extraer dato concreto.
3. Generar contenido aplicando:
   - **Hook fuerte primera linea** (pregunta, dato contraintuitivo, frase cortante)
   - Posicionamiento Mauro: "Arquitecto DevOps + IA aplicada", NO "experto en IA"
   - Sustento concreto: numero, ejemplo, mini-caso. Si no hay → pedir a Mauro, no inventar.
   - Cierre con insight o pregunta. NO CTA agresivo.
4. Aplicar **filtros anti-hype** (ver abajo). Si match → reescribir.
5. Guardar en `drafts/<format-group>/$(date +%Y-%m-%d)-<slug>.md` con frontmatter.
6. Mostrar a Mauro en chat:
   - Ruta archivo
   - Preview completo
   - 1 linea con sugerencia mejora (si hay)

## Filtros anti-hype (OBLIGATORIO)

Rechazar y reescribir si aparece:

- "Desbloquea", "transformacional", "revolucionario", "potencia tu", "lleva al siguiente nivel"
- "10 herramientas / prompts / trucos / secretos"
- "El futuro es X", "La IA va a Y"
- "Aprende X en N dias", "Domina X"
- Emojis decorativos (1 emoji estructural OK)
- Listas sin sustento
- Numeros inventados ("+300% productividad")
- Frases vacias: "es importante", "no olvides", "ten en cuenta"

## Estructura por formato

### linkedin-post (150-300 palabras)
1. Hook (1 linea)
2. Contexto/problema (2-3 lineas)
3. Insight (postura de Mauro)
4. Sustento (numero/ejemplo)
5. Cierre con pregunta

### linkedin-carousel (5-10 slides)
- Slide 1: hook visual
- Slides 2-N: una idea por slide
- Slide ultimo: pregunta o insight

### linkedin-article (1000-2500 palabras)
- TL;DR (3 lineas)
- Contexto/problema (~200w)
- Analisis con sub-secciones (~1500w)
- Anti-patrones (~200w)
- Que aplicar (~200w)
- Cierre

### x-thread (8-15 tweets, 280c max cada uno)
- T1: hook
- T2-N: progresion con dato/insight por tweet
- T-ultimo: cierre + invitacion suave

### ebook-chapter (~2000-4000 palabras)
- Apertura con caso/anecdota
- Concepto + framework
- Ejemplos reales con numeros
- Anti-patrones
- Checklist o accion concreta
- Cierre + bridge al siguiente capitulo

### demo-script (3-7 min, ~600-1200 palabras)
- 0:00-0:30 hook + problema
- 0:30-2:00 contexto + setup
- 2:00-5:00 demo paso a paso
- 5:00-6:00 resultado + numero
- 6:00-7:00 que aplicar + cierre

### outreach-msg (max 6 lineas)
- Linea 1: senal especifica detectada (mostrar que NO es plantilla)
- Linea 2: experiencia relevante de Mauro (1 frase)
- Linea 3: oferta especifica (auditoria/consultoria/agente)
- Linea 4: pregunta abierta (no "agendemos call")
- NO firma generica, NO links agresivos

## Ventajas Mauro a destacar

- DevOps enterprise real (no demos)
- Pipelines prod / incidentes reales
- DORA aplicado
- Observabilidad
- FinOps cloud
- IA aplicada aterrizada (no PoC eternas)
- Vision negocio + tecnica

## Frontmatter de salida

```yaml
---
format: <formato>
topic: <tema>
hook: <primera linea>
audience: <publico>
status: draft
intel_source: <ruta o "manual">
created: YYYY-MM-DD
length: <metrica>
---
```

## Reglas

- Espanol Chile natural. Sin marketing-speak.
- Si falta sustento concreto: detener y preguntar a Mauro.
- No publicar. No enviar. No tocar redes.
- No mover archivos a `published/` (eso es Mauro tras publicar real).
- Si Mauro pide variantes: generar 2-3 alternativas en archivos separados con sufijo `-v1`, `-v2`.
