"""Decision summary (T6) and paper detail directory (V7) HTML view generators."""

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .base import (STOPWORDS, CLUSTER_COLORS, _BASE_CSS, _THEME_JS,
                   _nav_bar, _html_shell, generate_labels)


def generate_decision_summary(
    clusters: Dict[str, int],
    gaps: Dict[str, Any],
    labels: Dict[int, str],
    output_path: str,
) -> str:
    """Generate T6: Decision Summary integrating V9 validation, V10 evaluation, V11 position.

    A client-side dashboard that reads all three localStorage keys and presents
    a unified decision view with cluster readiness, top bridges, and position context.

    Args:
        clusters: DOI -> cluster_id mapping
        gaps: gaps.json content (may be empty)
        labels: cluster_id -> label string
        output_path: destination file path

    Returns:
        output_path
    """
    cluster_counts: Counter = Counter(clusters.values())
    all_cids = sorted(cluster_counts.keys())

    cluster_info_js = json.dumps([
        {'id': cid, 'label': labels.get(cid, f'Cluster {cid}'), 'count': cluster_counts[cid]}
        for cid in all_cids
    ])
    colors_js = json.dumps(CLUSTER_COLORS)

    bridges = gaps.get('cross_cluster_bridges', []) if gaps else []
    bridge_data_js = json.dumps([
        {
            'id': f"{b.get('cluster_a', 0)}_{b.get('cluster_b', 0)}",
            'label_a': labels.get(b.get('cluster_a', 0), f"C{b.get('cluster_a', 0)}"),
            'label_b': labels.get(b.get('cluster_b', 0), f"C{b.get('cluster_b', 0)}"),
            'jaccard': round(b.get('entity_jaccard', 0), 3),
        }
        for b in bridges[:20]
    ])

    extra_css = """
.dec-grid { display:grid; grid-template-columns:1fr 1fr; gap:20px; margin-top:20px; }
@media (max-width:800px) { .dec-grid { grid-template-columns:1fr; } }
.dec-card { background:var(--card-bg); border:1px solid var(--border); border-radius:10px; padding:18px 20px; }
.dec-card h3 { margin:0 0 14px 0; font-size:1.05rem; }
.dec-full { grid-column:1/-1; }
.dec-stat-row { display:flex; gap:16px; flex-wrap:wrap; margin-bottom:20px; }
.dec-stat { background:var(--card-bg); border:1px solid var(--border); border-radius:8px; padding:14px 18px; min-width:150px; flex:1; }
.dec-stat .val { font-size:1.8rem; font-weight:700; color:var(--accent); }
.dec-stat .lbl { font-size:0.82rem; color:var(--text2); margin-top:2px; }
.dec-bar { height:8px; border-radius:4px; background:var(--border); margin-top:6px; overflow:hidden; }
.dec-bar .fill { height:100%; border-radius:4px; transition:width 0.3s; }
.dec-cluster-list { list-style:none; padding:0; margin:0; }
.dec-cluster-list li { display:flex; align-items:center; gap:8px; padding:5px 0; font-size:0.88rem; border-bottom:1px solid var(--border); }
.dec-cluster-list li:last-child { border-bottom:none; }
.dec-dot { width:10px; height:10px; border-radius:50%; flex-shrink:0; }
.dec-check { color:#2ecc71; font-weight:700; }
.dec-uncheck { color:var(--text2); }
.dec-bridge-list { list-style:none; padding:0; margin:0; }
.dec-bridge-list li { padding:6px 0; font-size:0.88rem; border-bottom:1px solid var(--border); display:flex; justify-content:space-between; }
.dec-bridge-list li:last-child { border-bottom:none; }
.dec-score { font-weight:600; color:var(--accent); }
.dec-pos-box { padding:16px; border-radius:8px; background:var(--bg2); text-align:center; }
.dec-pos-label { font-size:1.2rem; font-weight:600; margin-bottom:4px; }
.dec-pos-sub { font-size:0.85rem; color:var(--text2); }
"""

    body = f"""<h1>Decision Summary</h1>
<h2>Integrated view of your cluster validation, bridge evaluation, and research position</h2>

<div class="dec-stat-row" id="dec-stats"></div>

<div class="dec-grid">
  <div class="dec-card">
    <h3>My Position</h3>
    <div id="dec-position"><div class="dec-pos-box"><span class="dec-pos-label" style="color:var(--text2)">Not set</span><div class="dec-pos-sub">Select your position on the Overview page</div></div></div>
  </div>

  <div class="dec-card">
    <h3>Validation Progress</h3>
    <div id="dec-val-progress"></div>
    <div class="dec-bar"><div class="fill" id="dec-val-bar" style="width:0%;background:#2ecc71;"></div></div>
  </div>

  <div class="dec-card">
    <h3>Validated Clusters</h3>
    <ul class="dec-cluster-list" id="dec-clusters"></ul>
  </div>

  <div class="dec-card">
    <h3>Top Bridges (by evaluation)</h3>
    <ul class="dec-bridge-list" id="dec-bridges"></ul>
  </div>
</div>

<script>
var CLUSTERS = {cluster_info_js};
var COLORS = {colors_js};
var BRIDGES = {bridge_data_js};
var LS_VAL = 'papersift_cluster_validation';
var LS_POS = 'papersift_my_position';
var LS_EVAL = 'papersift_bridge_eval';

function buildDecision() {{
  var valState = {{}};
  try {{ valState = JSON.parse(localStorage.getItem(LS_VAL)) || {{}}; }} catch(e) {{}}
  var evalState = {{}};
  try {{ evalState = JSON.parse(localStorage.getItem(LS_EVAL)) || {{}}; }} catch(e) {{}}
  var posCid = localStorage.getItem(LS_POS) || '';

  // Stats
  var nClusters = CLUSTERS.length;
  var nValidated = 0;
  CLUSTERS.forEach(function(c) {{ if(valState[c.id]) nValidated++; }});
  var nEvaluated = 0;
  var totalAvg = 0;
  BRIDGES.forEach(function(b) {{
    var s = evalState[b.id];
    if(s) {{ nEvaluated++; totalAvg += (s.novelty + s.feasibility + s.interest) / 3; }}
  }});
  var avgScore = nEvaluated ? (totalAvg / nEvaluated).toFixed(1) : '—';

  document.getElementById('dec-stats').innerHTML =
    '<div class="dec-stat"><div class="val">' + nValidated + '/' + nClusters + '</div><div class="lbl">Clusters Validated</div></div>'
    + '<div class="dec-stat"><div class="val">' + nEvaluated + '/' + BRIDGES.length + '</div><div class="lbl">Bridges Evaluated</div></div>'
    + '<div class="dec-stat"><div class="val">' + avgScore + '</div><div class="lbl">Avg Bridge Score</div></div>'
    + '<div class="dec-stat"><div class="val">' + (posCid ? 'C' + posCid : '—') + '</div><div class="lbl">My Position</div></div>';

  // Validation progress bar
  var pct = nClusters ? (nValidated / nClusters * 100) : 0;
  document.getElementById('dec-val-progress').innerHTML = '<span style="font-size:0.88rem;color:var(--text2)">' + nValidated + ' of ' + nClusters + ' validated (' + Math.round(pct) + '%)</span>';
  document.getElementById('dec-val-bar').style.width = pct + '%';

  // Position
  if (posCid) {{
    var posCluster = CLUSTERS.find(function(c) {{ return String(c.id) === String(posCid); }});
    if (posCluster) {{
      var ci = CLUSTERS.indexOf(posCluster);
      var color = COLORS[ci % COLORS.length];
      document.getElementById('dec-position').innerHTML =
        '<div class="dec-pos-box" style="border-left:4px solid ' + color + '">'
        + '<div class="dec-pos-label">C' + posCluster.id + ': ' + escHtml(posCluster.label) + '</div>'
        + '<div class="dec-pos-sub">' + posCluster.count + ' papers in this cluster</div></div>';
    }}
  }}

  // Cluster list
  var clusterHtml = '';
  CLUSTERS.forEach(function(c, i) {{
    var validated = valState[c.id];
    var icon = validated ? '<span class="dec-check">✓</span>' : '<span class="dec-uncheck">○</span>';
    var posTag = String(c.id) === String(posCid) ? ' <strong style="color:var(--accent)">(You)</strong>' : '';
    clusterHtml += '<li>'
      + '<span class="dec-dot" style="background:' + COLORS[i % COLORS.length] + '"></span>'
      + icon + ' C' + c.id + ': ' + escHtml(c.label) + ' (' + c.count + ')' + posTag
      + '</li>';
  }});
  document.getElementById('dec-clusters').innerHTML = clusterHtml;

  // Bridges ranked
  var bridgeRows = BRIDGES.map(function(b) {{
    var s = evalState[b.id];
    var avg = s ? ((s.novelty + s.feasibility + s.interest) / 3).toFixed(1) : null;
    return {{label_a: b.label_a, label_b: b.label_b, avg: avg, evaluated: !!s}};
  }}).sort(function(a, b) {{
    if (!a.evaluated && !b.evaluated) return 0;
    if (!a.evaluated) return 1;
    if (!b.evaluated) return -1;
    return parseFloat(b.avg) - parseFloat(a.avg);
  }});

  var bridgeHtml = '';
  bridgeRows.slice(0, 10).forEach(function(r) {{
    var scoreHtml = r.evaluated ? '<span class="dec-score">' + r.avg + '/5</span>' : '<span style="color:var(--text2)">—</span>';
    bridgeHtml += '<li><span>' + escHtml(r.label_a) + ' ↔ ' + escHtml(r.label_b) + '</span>' + scoreHtml + '</li>';
  }});
  if (!bridgeRows.length) bridgeHtml = '<li style="color:var(--text2)">No bridge data available</li>';
  document.getElementById('dec-bridges').innerHTML = bridgeHtml;
}}

buildDecision();
window.addEventListener('focus', buildDecision);
</script>"""

    html = _html_shell('Decision Summary — PaperSift', 'decision', extra_css, body)
    Path(output_path).write_text(html, encoding='utf-8')
    return output_path


def generate_detail(
    papers: List[Dict[str, Any]],
    clusters: Dict[str, int],
    labels: Dict[int, str],
    output_path: str,
) -> str:
    """Generate V7: searchable, paginated paper directory.

    Args:
        papers: list of all paper dicts
        clusters: DOI -> cluster_id mapping
        labels: cluster_id -> label string
        output_path: destination file path

    Returns:
        output_path
    """
    # Build card data
    cards = []
    for p in sorted(papers, key=lambda x: x.get('year', 0) or 0, reverse=True):
        doi = p.get('doi', '')
        title = p.get('title', 'Unknown title')
        year = p.get('year', '')
        cid = clusters.get(doi)
        cluster_label = labels.get(cid, f'Cluster {cid}') if cid is not None else 'Unassigned'
        cluster_color = CLUSTER_COLORS[cid % len(CLUSTER_COLORS)] if cid is not None else '#aaaaaa'
        topics_raw = p.get('topics', []) or []
        topic_names: List[str] = []
        for t in topics_raw[:3]:
            if isinstance(t, str):
                topic_names.append(t)
            elif isinstance(t, dict):
                topic_names.append(t.get('display_name') or t.get('name') or '')
        topics_str = ', '.join(filter(None, topic_names))
        doi_url = f'https://doi.org/{doi}' if doi else ''
        cards.append({
            'title': title,
            'year': year,
            'doi': doi,
            'doi_url': doi_url,
            'cluster_label': cluster_label,
            'cluster_color': cluster_color,
            'topics': topics_str,
            'search_key': (title + ' ' + doi + ' ' + cluster_label).lower(),
        })

    # Build cluster options for filter dropdown
    cluster_counts: dict = {}
    for p in papers:
        doi = p.get('doi', '')
        cid = clusters.get(doi)
        if cid is not None:
            cl = labels.get(cid, f'Cluster {cid}')
            cluster_counts[cl] = cluster_counts.get(cl, 0) + 1

    cluster_options_html = '<option value="">All Clusters ({total})</option>'.format(total=len(cards))
    for cl_label in sorted(cluster_counts.keys()):
        cnt = cluster_counts[cl_label]
        cluster_options_html += f'\n      <option value="{cl_label}">{cl_label} ({cnt})</option>'

    extra_css = """
.filter-row { display: flex; gap: 12px; margin-bottom: 20px; align-items: stretch; }
.filter-row .search-bar { flex: 1; margin-bottom: 0; }
.search-bar input {
  width: 100%; padding: 12px 16px; font-size: 1rem; height: 100%;
  border: 1px solid var(--border); border-radius: 8px;
  background: var(--card); color: var(--text); outline: none;
}
.search-bar input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(52,152,219,0.15); }
.cluster-filter select {
  padding: 12px 16px; font-size: 0.95rem;
  border: 1px solid var(--border); border-radius: 8px;
  background: var(--card); color: var(--text); outline: none;
  min-width: 200px; cursor: pointer;
}
.cluster-filter select:focus { border-color: var(--accent); }
.stats { font-size: 0.9rem; color: var(--text2); margin-bottom: 16px; }
.cards-grid { display: flex; flex-direction: column; gap: 12px; }
.card {
  background: var(--card); border: 1px solid var(--border); border-radius: 8px;
  padding: 16px 18px; box-shadow: 0 1px 4px var(--shadow);
}
.card-title { font-size: 0.97rem; font-weight: 500; margin-bottom: 6px; }
.card-title a { color: var(--text); text-decoration: none; }
.card-title a:hover { color: var(--accent); text-decoration: underline; }
.card-meta { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; font-size: 0.82rem; color: var(--text2); }
.cluster-tag { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 0.78rem;
  font-weight: 500; color: #fff; }
.topic-tag { display: inline-block; padding: 2px 7px; border-radius: 10px; font-size: 0.78rem;
  background: var(--bg2); border: 1px solid var(--border); color: var(--text2); }
.pagination { display: flex; gap: 8px; justify-content: center; margin-top: 24px; flex-wrap: wrap; }
.page-btn {
  padding: 6px 14px; border: 1px solid var(--border); border-radius: 6px;
  background: var(--card); color: var(--text); cursor: pointer; font-size: 0.88rem;
}
.page-btn.active { background: var(--accent); color: #fff; border-color: var(--accent); }
.page-btn:hover:not(.active) { background: var(--bg2); }
"""

    body = f"""<h1>Paper Directory</h1>
<h2>{len(cards)} papers across all clusters</h2>
<div class="filter-row">
  <div class="cluster-filter">
    <select id="clusterFilter" onchange="doSearch()">
      {cluster_options_html}
    </select>
  </div>
  <div class="search-bar">
    <input type="text" id="searchInput" placeholder="Search by title, DOI, or cluster..." oninput="doSearch()">
  </div>
</div>
<div class="stats" id="statsBar">Showing all {len(cards)} papers</div>
<div class="cards-grid" id="cardsGrid"></div>
<div class="pagination" id="pagination"></div>
<script>
var ALL_CARDS = {json.dumps(cards)};
var PAGE_SIZE = 50;
var currentPage = 1;
var filtered = ALL_CARDS;

function escHtml(s) {{
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}}

function renderPage() {{
  var start = (currentPage - 1) * PAGE_SIZE;
  var slice = filtered.slice(start, start + PAGE_SIZE);
  var html = '';
  slice.forEach(function(c) {{
    var titleLink = c.doi_url
      ? '<a href="' + c.doi_url + '" target="_blank" rel="noopener">' + escHtml(c.title) + '</a>'
      : escHtml(c.title);
    var clusterTag = '<span class="cluster-tag" style="background:' + c.cluster_color + '">'
      + escHtml(c.cluster_label) + '</span>';
    var topicTags = c.topics ? c.topics.split(', ').filter(Boolean)
      .map(function(t) {{ return '<span class="topic-tag">' + escHtml(t) + '</span>'; }}).join('') : '';
    var doiSpan = c.doi ? '<span>DOI: ' + escHtml(c.doi) + '</span>' : '';
    html += '<div class="card">';
    html += '<div class="card-title">' + titleLink + '</div>';
    html += '<div class="card-meta">';
    html += (c.year ? '<span>' + c.year + '</span>' : '');
    html += clusterTag;
    html += topicTags;
    html += doiSpan;
    html += '</div></div>';
  }});
  document.getElementById('cardsGrid').innerHTML = html;

  // Pagination
  var totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  var paginationHtml = '';
  if (totalPages > 1) {{
    if (currentPage > 1) paginationHtml += '<button class="page-btn" onclick="goPage(' + (currentPage-1) + ')">&#8249; Prev</button>';
    var start_p = Math.max(1, currentPage - 2);
    var end_p = Math.min(totalPages, currentPage + 2);
    for (var p = start_p; p <= end_p; p++) {{
      var active = p === currentPage ? ' active' : '';
      paginationHtml += '<button class="page-btn' + active + '" onclick="goPage(' + p + ')">' + p + '</button>';
    }}
    if (currentPage < totalPages) paginationHtml += '<button class="page-btn" onclick="goPage(' + (currentPage+1) + ')">Next &#8250;</button>';
  }}
  document.getElementById('pagination').innerHTML = paginationHtml;
  document.getElementById('statsBar').textContent =
    'Showing ' + filtered.length + ' of {len(cards)} papers (page ' + currentPage + ' of ' + Math.max(1, totalPages) + ')';
}}

function goPage(p) {{
  currentPage = p;
  renderPage();
  window.scrollTo(0, 0);
}}

function doSearch() {{
  var q = document.getElementById('searchInput').value.toLowerCase().trim();
  var cl = document.getElementById('clusterFilter').value;
  filtered = ALL_CARDS;
  if (cl) {{
    filtered = filtered.filter(function(c) {{ return c.cluster_label === cl; }});
  }}
  if (q) {{
    filtered = filtered.filter(function(c) {{ return c.search_key.indexOf(q) !== -1; }});
  }}
  currentPage = 1;
  renderPage();
}}

renderPage();
</script>"""

    html = _html_shell('Paper Directory — PaperSift', 'papers', extra_css, body)
    Path(output_path).write_text(html, encoding='utf-8')
    return output_path
