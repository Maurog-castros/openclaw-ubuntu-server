#!/bin/bash
echo "# Trend Radar Technical Signal Collection - $(date)" > /home/mauro/openclaw-mauro/data/workspace/trend_radar_collection.md
echo "Generated at: $(date)" >> /home/mauro/openclaw-mauro/data/workspace/trend_radar_collection.md
echo "" >> /home/mauro/openclaw-mauro/data/workspace/trend_radar_collection.md

echo "## 1. Hacker News — Top 20 stories" >> /home/mauro/openclaw-mauro/data/workspace/trend_radar_collection.md
curl -s --max-time 10 https://hacker-news.firebaseio.com/v0/topstories.json \
  | jq '.[0:20]' | jq -r '.[]' | while read id; do
    curl -s --max-time 5 "https://hacker-news.firebaseio.com/v0/item/$id.json" \
      | jq -r '"- [\(.title // "?")](\(.url // "https://news.ycombinator.com/item?id=\(.id)")) — score:\(.score // 0) comments:\(.descendants // 0) by:\(.by // "?")"' 
  done >> /home/mauro/openclaw-mauro/data/workspace/trend_radar_collection.md

echo "" >> /home/mauro/openclaw-mauro/data/workspace/trend_radar_collection.md
echo "## 2. Reddit subs" >> /home/mauro/openclaw-mauro/data/workspace/trend_radar_collection.md
for sub in devops sre MachineLearning kubernetes selfhosted; do
  echo "### r/$sub" >> /home/mauro/openclaw-mauro/data/workspace/trend_radar_collection.md
  curl -s --max-time 10 -A "Mozilla/5.0 (intel-bot)" "https://www.reddit.com/r/$sub/hot.json?limit=15" \
    | jq -r '.data.children[]? | "- [\(.data.title)](https://reddit.com\(.data.permalink)) — score:\(.data.score) comments:\(.data.num_comments) flair:\(.data.link_flair_text // "")"' >> /home/mauro/openclaw-mauro/data/workspace/trend_radar_collection.md
done

echo "" >> /home/mauro/openclaw-mauro/data/workspace/trend_radar_collection.md
echo "## 3. GitHub Trending (daily, all languages)" >> /home/mauro/openclaw-mauro/data/workspace/trend_radar_collection.md

repos=$(curl -s --max-time 10 -A "Mozilla/5.0 (intel-bot)" "https://github.com/trending?since=daily" \
  | grep -oE 'href="/[^/]+/[^/"]+" data-view-component' \
  | head -25 \
  | sed 's|href="/||; s|"||; s| data-view-component||')

if [ -n "$repos" ]; then
  for repo in $repos; do
    curl -s --max-time 5 "https://api.github.com/repos/$repo" \
      | jq -r '"- \(.full_name) — \(.stargazers_count)⭐ — \(.description // "")"' >> /home/mauro/openclaw-mauro/data/workspace/trend_radar_collection.md
  done
else
  echo "No trending repos found or GitHub rate limited/blocked the scrape." >> /home/mauro/openclaw-mauro/data/workspace/trend_radar_collection.md
fi

echo "" >> /home/mauro/openclaw-mauro/data/workspace/trend_radar_collection.md
echo "## 4. GitHub Trending — topic search filters" >> /home/mauro/openclaw-mauro/data/workspace/trend_radar_collection.md
for topic in devops mlops observability kubernetes; do
  echo "### topic:$topic" >> /home/mauro/openclaw-mauro/data/workspace/trend_radar_collection.md
  push_date=$(date -d '7 days ago' +%Y-%m-%d 2>/dev/null || date -v-7d +%Y-%m-%d 2>/dev/null || echo "2026-05-20")
  curl -s --max-time 10 "https://api.github.com/search/repositories?q=topic:$topic+pushed:>$push_date&sort=stars&order=desc&per_page=10" \
    | jq -r '.items[]? | "- \(.full_name) — \(.stargazers_count)⭐ — \(.description // "")"' >> /home/mauro/openclaw-mauro/data/workspace/trend_radar_collection.md
done

echo "Collection finished successfully."
