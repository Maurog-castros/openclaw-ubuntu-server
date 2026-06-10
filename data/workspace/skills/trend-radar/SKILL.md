---
name: trend-radar
description: "Scrapea fuentes publicas (HN, Reddit r/devops r/sre r/MachineLearning, GitHub Trending) y devuelve raw data tecnica del dia. NO produce el reporte final — solo recolecta. Trigger: 'trend radar', 'que paso hoy en devops', 'scan tendencias', 'daily intel raw'."
---

# trend-radar — Recolector de senales tecnicas

Skill de recoleccion. Output crudo. El agente que invoca debe sintetizar.

## Procedimiento

Ejecutar en paralelo los bloques. Si una fuente falla, continuar con las demas.

### 1. Hacker News — Top 20 stories

```sh
curl -s --max-time 10 https://hacker-news.firebaseio.com/v0/topstories.json \
  | jq '.[0:20]' | jq -r '.[]' | while read id; do
    curl -s --max-time 5 "https://hacker-news.firebaseio.com/v0/item/$id.json" \
      | jq -r '"- [\(.title // "?")](\(.url // "https://news.ycombinator.com/item?id=\(.id)")) — score:\(.score // 0) comments:\(.descendants // 0) by:\(.by // "?")"' 
  done
```

### 2. Reddit subs

Para cada sub en `devops sre MachineLearning kubernetes selfhosted`:

```sh
for sub in devops sre MachineLearning kubernetes selfhosted; do
  echo "## r/$sub"
  curl -s --max-time 10 -A "Mozilla/5.0 (intel-bot)" "https://www.reddit.com/r/$sub/hot.json?limit=15" \
    | jq -r '.data.children[] | "- [\(.data.title)](https://reddit.com\(.data.permalink)) — score:\(.data.score) comments:\(.data.num_comments) flair:\(.data.link_flair_text // "")"'
done
```

### 3. GitHub Trending (daily, all languages)

```sh
curl -s --max-time 10 -A "Mozilla/5.0 (intel-bot)" "https://github.com/trending?since=daily" \
  | grep -oE 'href="/[^/]+/[^/"]+" data-view-component' \
  | head -25 \
  | sed 's|href="/||; s|"||; s| data-view-component||'
```

Para cada repo:

```sh
curl -s --max-time 5 "https://api.github.com/repos/$repo" \
  | jq -r '"- \(.full_name) — \(.stargazers_count)⭐ — \(.description // "")"'
```

### 4. GitHub Trending — filtros tecnicos

Repos topic `devops`, `mlops`, `observability`, `kubernetes`:

```sh
for topic in devops mlops observability kubernetes; do
  echo "## topic:$topic"
  curl -s --max-time 10 "https://api.github.com/search/repositories?q=topic:$topic+pushed:>$(date -d '7 days ago' +%Y-%m-%d)&sort=stars&order=desc&per_page=10" \
    | jq -r '.items[] | "- \(.full_name) — \(.stargazers_count)⭐ — \(.description // "")"'
done
```

## Output

Devolver markdown organizado por seccion. No filtrar ni sintetizar — eso es trabajo del agente caller.

## Reglas

- Timeout corto (`--max-time`). Si una fuente cae, continuar.
- User-Agent siempre presente en Reddit/GitHub.
- No persiste nada — solo devuelve texto.
- Si `jq` falta: instalar via `apk add jq` o `apt install -y jq`.

## Argumentos opcionales

- `subs=<lista coma>` → cambia lista Reddit
- `topics=<lista coma>` → cambia lista topics GitHub
- `hn_limit=N` → cambia top N HN (default 20)
