---
product: agente-rag-corporativo
ticket_usd: 3000-15000
duracion: 4-8 semanas
nivel_esfuerzo: alto
---

# Agente RAG Corporativo

## Para quien

- Empresas con documentacion fragmentada (Confluence + Notion + Drive + Slack)
- Onboarding lento de nuevos ingenieros
- Soporte interno saturado respondiendo lo mismo

## Que incluye

- Diseno arquitectura (Ollama/local o cloud)
- Ingest pipeline (conectores docs)
- Embeddings + vector store (ChromaDB / pgvector)
- UI minima (Slack bot, Teams, o web)
- Eval suite (preguntas gold + accuracy)
- Documentacion + handover

## NO incluye

- Mantenimiento post-handover (separado, mensualizado)
- Integraciones custom no listadas (cotizadas aparte)

## Stack tipico

- LLM: Ollama local (Qwen2.5 14B) o Gemini
- Vector: ChromaDB / pgvector
- Orquestacion: Python custom o LangChain minimo
- UI: Slack bot + web simple

## Pricing

- MVP (1 fuente, 1 UI): USD $3.000-$5.000
- Standard (3 fuentes, 1 UI, eval suite): USD $7.000-$10.000
- Enterprise (multi-fuente, multi-UI, on-prem, training): USD $12.000-$15.000+

## Como cerrarla

- Senal: queja docs internas + tamano equipo >30 + adopcion herramientas tipo Notion/Confluence
- Pilot 2-3 semanas como entry ($2-3k) -> full implementation
