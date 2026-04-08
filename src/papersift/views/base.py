"""Base constants, CSS/JS helpers, and shared utilities for PaperSift HTML views."""

from collections import Counter, defaultdict
from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STOPWORDS = {
    'the', 'a', 'an', 'of', 'in', 'for', 'to', 'and', 'with', 'on',
    'using', 'towards', 'based', 'new', 'novel', 'large', 'via',
    'from', 'single', 'multi', 'through', 'across', 'into', 'between',
    'among', 'how', 'what', 'why', 'when', 'where', 'which', 'who',
    'that', 'this', 'these', 'those', 'its', 'their', 'our', 'are',
    'is', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
    'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may',
    'might', 'can', 'not', 'by', 'at', 'as', 'or', 'but', 'if',
    'then', 'than', 'so', 'up', 'out', 'about', 'after', 'before',
    'during', 'while', 'under', 'over', 'just', 'also', 'only',
    'more', 'most', 'both', 'each', 'all', 'any', 'some', 'such',
    'paper', 'study', 'approach', 'method', 'framework', 'system',
    'analysis', 'model', 'models', 'data', 'results', 'performance',
    'applications', 'review', 'survey', 'toward', 'towards', 'high',
    'low', 'deep', 'learning', 'based', 'driven', 'enabled', 'enhanced',
}

# 12-color qualitative palette
CLUSTER_COLORS = [
    '#3498db', '#e74c3c', '#2ecc71', '#f39c12', '#9b59b6',
    '#1abc9c', '#e67e22', '#34495e', '#e91e63', '#00bcd4',
    '#8bc34a', '#ff5722',
]

# Shared CSS variables and base styles
_BASE_CSS = """
:root {
  --bg: #ffffff; --bg2: #f8f9fa; --text: #212529; --text2: #495057;
  --card: #ffffff; --border: #dee2e6; --accent: #3498db; --accent2: #2ecc71;
  --shadow: rgba(0,0,0,0.08);
  --card-bg: #ffffff; --hover-bg: #f0f0f0; --text1: #212529;
}
[data-theme="dark"] {
  --bg: #1a1a2e; --bg2: #16213e; --text: #e8e8e8; --text2: #adb5bd;
  --card: #0f3460; --border: #2c3e6b; --accent: #e94560; --accent2: #53d769;
  --shadow: rgba(0,0,0,0.3);
  --card-bg: #0f3460; --hover-bg: #1a2744; --text1: #e8e8e8;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: var(--bg); color: var(--text); min-height: 100vh; }
.container { max-width: 1200px; margin: 0 auto; padding: 24px 20px; }
h1 { font-size: 1.6rem; margin-bottom: 8px; }
h2 { font-size: 1.2rem; margin-bottom: 16px; color: var(--text2); font-weight: 500; }
.chart-wrap { width: 100%; height: 600px; background: var(--card);
              border: 1px solid var(--border); border-radius: 8px;
              box-shadow: 0 2px 8px var(--shadow); margin-bottom: 24px; }
"""

_THEME_JS = """
function toggleTheme() {
  var html = document.documentElement;
  var cur = html.getAttribute('data-theme') || 'light';
  var next = cur === 'dark' ? 'light' : 'dark';
  html.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);
  if (typeof onThemeChange === 'function') onThemeChange(next);
}
(function() {
  var saved = localStorage.getItem('theme');
  if (saved) document.documentElement.setAttribute('data-theme', saved);
})();
function escHtml(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');}
function getLS(k){try{return localStorage.getItem(k);}catch(e){return null;}}
function setLS(k,v){try{localStorage.setItem(k,v);}catch(e){}}
"""


def _nav_bar(active: str) -> str:
    """Return nav bar HTML with the active page highlighted."""
    pages = [
        ('overview.html', 'Overview'),
        ('bridges.html', 'Bridges'),
        ('ranking.html', 'Ranking'),
        ('timeline.html', 'Timeline'),
        ('detail.html', 'Papers'),
        ('decision.html', 'Decision'),
    ]
    links = []
    for href, label in pages:
        style = 'font-weight:700; color:var(--accent);' if label.lower() == active.lower() else 'color:var(--text);'
        links.append(
            f'<a href="{href}" style="text-decoration:none; padding:4px 8px; '
            f'border-radius:4px; {style}">{label}</a>'
        )
    links_html = '\n  '.join(links)
    return f"""<nav style="display:flex; gap:16px; align-items:center; padding:12px 20px;
  background:var(--bg2); border-bottom:1px solid var(--border);
  position:sticky; top:0; z-index:100;">
  {links_html}
  <span style="margin-left:auto;">
    <button onclick="toggleTheme()" style="background:none; border:1px solid var(--border);
      color:var(--text); padding:4px 10px; border-radius:4px; cursor:pointer; font-size:1rem;">
      🌓
    </button>
  </span>
</nav>"""


def _html_shell(title: str, active_page: str, head_extra: str, body: str) -> str:
    """Wrap content in a full HTML document with nav, theme, and Plotly CDN."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<script src="plotly.min.js" onerror="this.onerror=null;this.src='https://cdn.plot.ly/plotly-2.35.2.min.js'"></script>
<style>
{_BASE_CSS}
{head_extra}
</style>
</head>
<body>
{_nav_bar(active_page)}
<div class="container">
{body}
</div>
<script>
{_THEME_JS}
</script>
</body>
</html>"""


def generate_labels(clusters: Dict[str, int], papers: List[Dict[str, Any]]) -> Dict[int, str]:
    """Auto-generate cluster labels from top-3 frequent title words.

    Args:
        clusters: mapping of DOI -> cluster_id (int)
        papers: list of paper dicts with at least 'doi' and 'title' fields

    Returns:
        dict mapping cluster_id (int) -> label string "Word1 + Word2 + Word3"
    """
    # Build doi -> title lookup
    doi_to_title: Dict[str, str] = {}
    for p in papers:
        doi = p.get('doi', '')
        title = p.get('title', '')
        if doi and title:
            doi_to_title[doi] = title

    # Pre-aggregate word counts per cluster (O(N) single pass)
    cluster_counts: Dict[int, Counter] = defaultdict(Counter)
    for doi, cid in clusters.items():
        title = doi_to_title.get(doi, '')
        if not title:
            continue
        for w in title.lower().split():
            # Strip punctuation
            w = w.strip('.,;:!?()[]{}"\'-')
            if len(w) >= 4 and w not in STOPWORDS and w.isalpha():
                cluster_counts[cid][w] += 1

    labels: Dict[int, str] = {}
    for cid, counter in cluster_counts.items():
        if not counter:
            labels[cid] = f'Cluster {cid}'
            continue
        top3 = [w.capitalize() for w, _ in counter.most_common(3)]
        labels[cid] = ' + '.join(top3) if top3 else f'Cluster {cid}'

    # Fill in any cluster IDs that had no papers
    all_cids = set(clusters.values())
    for cid in all_cids:
        if cid not in labels:
            labels[cid] = f'Cluster {cid}'

    return labels
