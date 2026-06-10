const https = require('https');
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

// Helper to fetch JSON from URL with timeout
function fetchJson(url, timeout = 10000) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, { timeout, headers: { 'User-Agent': 'Mozilla/5.0 (intel-bot)', 'Accept': 'application/json,text/html;q=0.9,*/*;q=0.8' } }, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          resolve(JSON.parse(data));
        } catch (e) {
          console.error(`JSON parse error for ${url}:`, e.message.substring(0, 100));
          resolve(null);
        }
      });
    });
    req.on('error', reject);
    req.on('timeout', () => {
      req.destroy();
      reject(new Error('Timeout'));
    });
  });
}

// Helper to fetch HTML and parse with regex
function fetchHtml(url, timeout = 10000) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, { timeout, headers: { 'User-Agent': 'Mozilla/5.0 (intel-bot)', 'Accept': 'application/rss+xml,application/atom+xml,application/xml,text/xml,text/html;q=0.8' } }, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => resolve(data));
    });
    req.on('error', reject);
    req.on('timeout', () => {
      req.destroy();
      reject(new Error('Timeout'));
    });
  });
}


function decodeXml(value) {
  return (value || '')
    .replace(/<!\[CDATA\[(.*?)\]\]>/gs, '$1')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&#(\d+);/g, (_, code) => String.fromCharCode(Number(code)))
    .replace(/<[^>]+>/g, '')
    .trim();
}


function fetchRedditRss(sub) {
  return execFileSync('curl', [
    '-s', '--max-time', '10', '-A', 'Mozilla/5.0 (intel-bot)',
    `https://www.reddit.com/r/${sub}/.rss`
  ], { encoding: 'utf8', maxBuffer: 1024 * 1024 });
}

function parseRedditRss(xml, limit = 5) {
  const entries = [];
  const entryRegex = /<entry[\s\S]*?<\/entry>/g;
  let match;
  while ((match = entryRegex.exec(xml)) !== null && entries.length < limit) {
    const block = match[0];
    const title = decodeXml((block.match(/<title[^>]*>([\s\S]*?)<\/title>/) || [])[1]);
    const link = (block.match(/<link[^>]*href="([^"]+)"/) || [])[1] || decodeXml((block.match(/<id[^>]*>([\s\S]*?)<\/id>/) || [])[1]);
    if (title && link) entries.push({ title, link });
  }
  return entries;
}

// Parse trending repos from GitHub HTML
function parseTrendingRepos(html) {
  const repoRegex = /href="(\/[^/]+\/[^/"&?]+)"/g;
  const repos = new Set();
  let match;
  while ((match = repoRegex.exec(html)) !== null && repos.size < 25) {
    if (match[1].includes('trending')) continue; // Skip URL params
    if (!match[1].startsWith('/search')) {
      repos.add(match[1]);
    }
  }
  return Array.from(repos).slice(0, 25);
}

async function main() {
  const report = [];

  report.push("# Hacker News Top 20");
  try {
    const topIds = await fetchJson('https://hacker-news.firebaseio.com/v0/topstories.json');
    if (topIds && Array.isArray(topIds)) {
      for (let i = 0; i < Math.min(20, topIds.length); i++) {
        const item = await fetchJson(`https://hacker-news.firebaseio.com/v0/item/${topIds[i]}.json`);
        if (item) {
          report.push(`- [${item.title || '?'}](${item.url || `https://news.ycombinator.com/item?id=${item.id}`}) — score:${item.score || 0} comments:${item.descendants || 0}`);
        }
      }
    }
  } catch (e) {
    console.error("HN fetch error:", e.message);
  }

  report.push("\n## Reddit r/devops r/sre r/MachineLearning");
  const subs = ['devops', 'sre', 'MachineLearning'];
  for (const sub of subs) {
    try {
      const rss = fetchRedditRss(sub);
      const posts = parseRedditRss(rss, 5);
      report.push(`\n### r/${sub}`);
      if (posts.length === 0) {
        report.push('- Sin datos RSS disponibles hoy');
      }
      for (const post of posts.slice(0, 5)) {
        report.push(`- [${post.title}](${post.link})`);
      }
    } catch (e) {
      console.error(`Reddit ${sub} RSS error:`, e.message);
      report.push(`\n### r/${sub}`);
      report.push('- Reddit RSS no disponible hoy');
    }
  }

  report.push("\n## GitHub Trending (Daily)");
  try {
    const html = await fetchHtml('https://github.com/trending?since=daily');
    if (html) {
      const repos = parseTrendingRepos(html);
      for (const repo of repos.slice(0, 15)) {
        report.push(`- [${repo}](https://github.com${repo}) — trending daily`);
      }
    }
  } catch (e) {
    console.error("GitHub Trending error:", e.message);
  }

  report.push("\n## GitHub Topics (DevOps/MLOps/Observability/K8s)");
  const topics = ['devops', 'mlops', 'observability', 'kubernetes'];
  for (const topic of topics) {
    try {
      const url = `https://api.github.com/search/repositories?q=topic:${topic}&sort=stars&order=desc&per_page=5`;
      const data = await fetchJson(url);
      if (data && data.items) {
        report.push(`\n### topic:${topic}`);
        for (const item of data.items.slice(0, 3)) {
          report.push(`- ${item.full_name} — ⭐${item.stargazers_count} — ${item.description || ''}`);
        }
      }
    } catch (e) {
      console.error(`Topic ${topic} error:`, e.message);
    }
  }

  // Output to file and stdout
  const output = report.join('\n');
  const preferredOut = '/home/node/.openclaw/workspace/marketing/intel/trends_raw.md';
  const fallbackOut = path.join(process.cwd(), 'trends_raw.md');
  const outPath = fs.existsSync(path.dirname(preferredOut)) ? preferredOut : fallbackOut;
  fs.writeFileSync(outPath, output);
  console.log(output);
}

main();
