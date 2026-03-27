"""Cluster overview (V2) and drill-down (V5) HTML view generators."""

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .base import (STOPWORDS, CLUSTER_COLORS, _BASE_CSS, _THEME_JS,
                   _nav_bar, _html_shell, generate_labels)


def generate_overview(
    clusters: Dict[str, int],
    papers: List[Dict[str, Any]],
    labels: Dict[int, str],
    output_path: str,
) -> str:
    """Generate V2: treemap overview of all clusters.

    Args:
        clusters: DOI -> cluster_id mapping
        papers: list of paper dicts
        labels: cluster_id -> label string
        output_path: destination file path

    Returns:
        output_path
    """
    # Count papers per cluster
    cluster_counts: Counter = Counter(clusters.values())
    all_cids_raw = sorted(cluster_counts.keys())

    # T5: Collapse to top 20 + Others when >20 clusters
    MAX_TREEMAP_CLUSTERS = 20
    others_count = 0
    if len(all_cids_raw) > MAX_TREEMAP_CLUSTERS:
        # Sort by count descending, take top 20
        sorted_by_count = sorted(all_cids_raw, key=lambda c: cluster_counts[c], reverse=True)
        top_cids = sorted_by_count[:MAX_TREEMAP_CLUSTERS]
        others_count = sum(cluster_counts[c] for c in sorted_by_count[MAX_TREEMAP_CLUSTERS:])
        all_cids = sorted(top_cids)
    else:
        all_cids = all_cids_raw

    # Top entities per cluster (top 5 for hover)
    doi_to_title = {p.get('doi', ''): p.get('title', '') for p in papers if p.get('doi')}
    cluster_entities: Dict[int, str] = {}
    for cid in all_cids_raw:
        words: List[str] = []
        for doi, c in clusters.items():
            if c != cid:
                continue
            title = doi_to_title.get(doi, '')
            for w in title.lower().split():
                w = w.strip('.,;:!?()[]{}"\'-')
                if len(w) >= 4 and w not in STOPWORDS and w.isalpha():
                    words.append(w)
        top = [w.capitalize() for w, _ in Counter(words).most_common(5)]
        cluster_entities[cid] = ', '.join(top) if top else ''

    # Build treemap data
    ids = ['All'] + [f'C{cid}' for cid in all_cids]
    parents = [''] + ['All'] * len(all_cids)
    values = [0] + [cluster_counts[cid] for cid in all_cids]
    text_labels = ['All Papers'] + [
        f'{labels.get(cid, f"Cluster {cid}")}<br>{cluster_counts[cid]} papers'
        for cid in all_cids
    ]
    customdata = [''] + [cluster_entities.get(cid, '') for cid in all_cids]
    colors = ['#cccccc'] + [CLUSTER_COLORS[i % len(CLUSTER_COLORS)] for i in range(len(all_cids))]

    # T5: Append "Others" bucket if clusters were collapsed
    if others_count > 0:
        n_others = len(all_cids_raw) - MAX_TREEMAP_CLUSTERS
        ids.append('Others')
        parents.append('All')
        values.append(others_count)
        text_labels.append(f'{n_others} other clusters<br>{others_count} papers')
        customdata.append('')
        colors.append('#95a5a6')

    treemap_data = {
        'type': 'treemap',
        'ids': ids,
        'labels': text_labels,
        'parents': parents,
        'values': values,
        'customdata': customdata,
        'hovertemplate': '<b>%{label}</b><br>Top entities: %{customdata}<extra></extra>',
        'marker': {'colors': colors},
        'textfont': {'size': 13},
    }

    # JavaScript for click-through navigation to drill-down pages
    click_js = """
var gd = document.getElementById('chart');
gd.on('plotly_click', function(data) {
  if (!data.points || !data.points.length) return;
  var pt = data.points[0];
  var id = pt.id;
  if (!id || id === 'All') return;
  var cid = id.replace('C', '');
  window.location.href = 'cluster_' + cid + '.html';
});
"""

    # V9: Cluster validation data + V11: positioning data for JS
    cluster_info_js = json.dumps([
        {'id': cid, 'label': labels.get(cid, f'Cluster {cid}'), 'count': cluster_counts[cid]}
        for cid in all_cids_raw
    ])
    treemap_json = json.dumps({'data': [treemap_data], 'layout': {
        'margin': {'t': 10, 'l': 10, 'r': 10, 'b': 10},
        'paper_bgcolor': 'rgba(0,0,0,0)',
        'plot_bgcolor': 'rgba(0,0,0,0)',
        'font': {'family': '-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif'},
    }})
    colors_js = json.dumps(CLUSTER_COLORS)

    extra_css = """
.l6-panel { margin-top:24px; padding:18px 20px; border:1px solid var(--border); border-radius:10px; background:var(--card-bg); }
.l6-panel h3 { margin:0 0 12px 0; font-size:1.05rem; }
.l6-grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(220px,1fr)); gap:8px; }
.l6-item { display:flex; align-items:center; gap:8px; padding:6px 10px; border-radius:6px; font-size:0.9rem; }
.l6-item:hover { background:var(--hover-bg); }
.l6-item input[type=checkbox] { width:16px; height:16px; accent-color:#2ecc71; cursor:pointer; }
.l6-item .dot { width:10px; height:10px; border-radius:50%; flex-shrink:0; }
.l6-item .info { flex:1; }
.l6-item .count { color:var(--text2); font-size:0.8rem; }
.l6-item.validated { opacity:1; }
.l6-item.unvalidated { opacity:0.65; }
.l6-progress { margin-top:10px; font-size:0.85rem; color:var(--text2); }
.l6-progress .bar { height:6px; border-radius:3px; background:var(--border); margin-top:4px; overflow:hidden; }
.l6-progress .fill { height:100%; background:#2ecc71; border-radius:3px; transition:width 0.3s; }
.position-section { margin-top:16px; display:flex; align-items:center; gap:12px; }
.position-section select { padding:6px 12px; border-radius:6px; border:1px solid var(--border); background:var(--card-bg); color:var(--text1); font-size:0.9rem; }
.position-badge { display:inline-block; padding:3px 10px; border-radius:12px; background:#3498db; color:#fff; font-size:0.8rem; }
.eval-btn { padding:7px 16px; border-radius:6px; border:1px solid var(--border); background:var(--card-bg); color:var(--text1); cursor:pointer; font-size:0.85rem; }
.eval-btn:hover { background:var(--hover-bg); }
"""

    body = f"""<h1>Cluster Overview</h1>
<h2>Click a cluster to explore its papers</h2>
<div id="chart" class="chart-wrap"></div>

<!-- V11: My Position -->
<div class="l6-panel">
  <h3>My Research Position</h3>
  <div class="position-section">
    <label for="pos-select">I am closest to:</label>
    <select id="pos-select" onchange="savePosition()">
      <option value="">— Select cluster —</option>
    </select>
    <span id="pos-badge"></span>
  </div>
</div>

<!-- V9: Cluster Validation -->
<div class="l6-panel">
  <h3>Cluster Validation</h3>
  <p style="font-size:0.85rem;color:var(--text2);margin:0 0 10px 0;">Check each cluster after verifying it matches your domain knowledge.</p>
  <div class="l6-grid" id="val-grid"></div>
  <div class="l6-progress"><span id="val-status">0 / 0 validated</span><div class="bar"><div class="fill" id="val-bar" style="width:0%"></div></div></div>
  <div style="margin-top:10px;">
    <button class="eval-btn" onclick="document.getElementById('val-import').click()">Import JSON</button>
    <input type="file" id="val-import" accept=".json" style="display:none" onchange="importValidation(this)">
  </div>
</div>

<script>
var DATA = {treemap_json};
Plotly.newPlot('chart', DATA.data, DATA.layout, {{responsive: true, displayModeBar: false}});
{click_js}
function onThemeChange(theme) {{
  var fc = theme === 'dark' ? '#e8e8e8' : '#212529';
  Plotly.relayout('chart', {{'font.color': fc}});
}}

// V9+V11 localStorage interactivity
var CLUSTERS = {cluster_info_js};
var COLORS = {colors_js};
var LS_VAL = 'papersift_cluster_validation';
var LS_POS = 'papersift_my_position';

function loadValidation() {{
  try {{ return JSON.parse(localStorage.getItem(LS_VAL)) || {{}}; }} catch(e) {{ return {{}}; }}
}}
function saveValidation(state) {{
  localStorage.setItem(LS_VAL, JSON.stringify(state));
  updateProgress(state);
}}
function updateProgress(state) {{
  var n = CLUSTERS.length, v = 0;
  CLUSTERS.forEach(function(c) {{ if(state[c.id]) v++; }});
  document.getElementById('val-status').textContent = v + ' / ' + n + ' validated';
  document.getElementById('val-bar').style.width = (n ? (v/n*100) : 0) + '%';
}}
function buildValidationGrid() {{
  var grid = document.getElementById('val-grid');
  var state = loadValidation();
  CLUSTERS.forEach(function(c, i) {{
    var div = document.createElement('div');
    div.className = 'l6-item ' + (state[c.id] ? 'validated' : 'unvalidated');
    div.innerHTML = '<input type="checkbox" ' + (state[c.id] ? 'checked' : '') + '>'
      + '<span class="dot" style="background:' + COLORS[i % COLORS.length] + '"></span>'
      + '<span class="info">' + c.label + ' <span class="count">(' + c.count + ')</span></span>';
    div.querySelector('input').addEventListener('change', function(e) {{
      state[c.id] = e.target.checked;
      div.className = 'l6-item ' + (e.target.checked ? 'validated' : 'unvalidated');
      saveValidation(state);
    }});
    grid.appendChild(div);
  }});
  updateProgress(state);
}}
function buildPositionSelect() {{
  var sel = document.getElementById('pos-select');
  CLUSTERS.forEach(function(c, i) {{
    var opt = document.createElement('option');
    opt.value = c.id;
    opt.textContent = 'C' + c.id + ': ' + c.label;
    sel.appendChild(opt);
  }});
  var saved = localStorage.getItem(LS_POS);
  if (saved) {{ sel.value = saved; showBadge(saved); }}
}}
function savePosition() {{
  var v = document.getElementById('pos-select').value;
  if (v) {{ localStorage.setItem(LS_POS, v); }} else {{ localStorage.removeItem(LS_POS); }}
  showBadge(v);
  highlightCluster(v);
}}
function showBadge(cid) {{
  var badge = document.getElementById('pos-badge');
  if (!cid) {{ badge.innerHTML = ''; return; }}
  var c = CLUSTERS.find(function(x) {{ return String(x.id) === String(cid); }});
  badge.innerHTML = c ? '<span class="position-badge">My cluster: C' + c.id + '</span>' : '';
}}
function highlightCluster(cid) {{
  var ids = DATA.data[0].ids;
  var widths = ids.map(function(id) {{ return id === 'C' + cid ? 4 : 0; }});
  var lc = ids.map(function(id) {{ return id === 'C' + cid ? '#f1c40f' : 'rgba(0,0,0,0)'; }});
  Plotly.restyle('chart', {{'marker.line.width': [widths], 'marker.line.color': [lc]}}, [0]);
}}
function importValidation(input) {{
  if (!input.files.length) return;
  var reader = new FileReader();
  reader.onload = function(e) {{
    try {{
      var data = JSON.parse(e.target.result);
      localStorage.setItem(LS_VAL, JSON.stringify(data));
      document.getElementById('val-grid').innerHTML = '';
      buildValidationGrid();
    }} catch(err) {{ alert('Invalid JSON file'); }}
  }};
  reader.readAsText(input.files[0]);
  input.value = '';
}}
buildValidationGrid();
buildPositionSelect();
highlightCluster(localStorage.getItem(LS_POS) || '');
</script>"""

    html = _html_shell('Cluster Overview — PaperSift', 'overview', extra_css, body)
    Path(output_path).write_text(html, encoding='utf-8')
    return output_path


def generate_drilldown(
    cluster_id: int,
    cluster_papers: List[Dict[str, Any]],
    labels: Dict[int, str],
    output_path: str,
) -> str:
    """Generate V5: sortable, filterable paper table for one cluster.

    Args:
        cluster_id: integer cluster ID
        cluster_papers: list of paper dicts in this cluster
        labels: cluster_id -> label string
        output_path: destination file path

    Returns:
        output_path
    """
    label = labels.get(cluster_id, f'Cluster {cluster_id}')

    # Prepare row data for inlining as JSON
    rows = []
    for p in sorted(cluster_papers, key=lambda x: x.get('year', 0) or 0, reverse=True):
        doi = p.get('doi', '')
        title = p.get('title', 'Unknown')
        year = p.get('year', '')
        cited = p.get('cited_by_count', 0) or 0
        topics_raw = p.get('topics', []) or []
        # topics may be strings or dicts
        topic_names: List[str] = []
        for t in topics_raw[:2]:
            if isinstance(t, str):
                topic_names.append(t)
            elif isinstance(t, dict):
                topic_names.append(t.get('display_name') or t.get('name') or '')
        topics_str = ', '.join(filter(None, topic_names))
        doi_url = f'https://doi.org/{doi}' if doi else ''
        rows.append({
            'title': title,
            'year': year,
            'cited': cited,
            'topics': topics_str,
            'doi': doi,
            'doi_url': doi_url,
        })

    extra_css = """
.filter-bar { margin-bottom: 16px; }
.filter-bar input {
  width: 100%; padding: 10px 14px; font-size: 0.95rem;
  border: 1px solid var(--border); border-radius: 6px;
  background: var(--card); color: var(--text); outline: none;
}
.filter-bar input:focus { border-color: var(--accent); }
table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
thead th {
  text-align: left; padding: 10px 12px; border-bottom: 2px solid var(--border);
  cursor: pointer; user-select: none; color: var(--text2); white-space: nowrap;
}
thead th:hover { color: var(--accent); }
thead th.sorted { color: var(--accent); }
tbody tr:hover { background: var(--bg2); }
tbody td { padding: 9px 12px; border-bottom: 1px solid var(--border); vertical-align: top; }
tbody td.title-cell { max-width: 480px; }
tbody td.title-cell a { color: var(--text); text-decoration: none; }
tbody td.title-cell a:hover { color: var(--accent); text-decoration: underline; }
.badge { display:inline-block; font-size:0.75rem; padding:2px 7px;
  background:var(--bg2); border:1px solid var(--border); border-radius:10px;
  color:var(--text2); margin-right:4px; }
.back-link { display:inline-block; margin-bottom:20px; color:var(--accent);
  text-decoration:none; font-size:0.9rem; }
.back-link:hover { text-decoration:underline; }
"""

    body = f"""<a href="overview.html" class="back-link">← Back to Overview</a>
<h1>{label}</h1>
<h2>{len(rows)} papers</h2>
<div class="filter-bar">
  <input type="text" id="filterInput" placeholder="Filter by title or DOI..." oninput="applyFilter()">
</div>
<div style="overflow-x:auto;">
<table id="paperTable">
  <thead>
    <tr>
      <th onclick="sortTable(0)">Title</th>
      <th onclick="sortTable(1)">Year</th>
      <th onclick="sortTable(2)">Cited by</th>
      <th onclick="sortTable(3)">Topics</th>
    </tr>
  </thead>
  <tbody id="tableBody"></tbody>
</table>
</div>
<script>
var ROWS = {json.dumps(rows)};
var sortCol = 1, sortAsc = false;

function renderRows(data) {{
  var tbody = document.getElementById('tableBody');
  var html = '';
  data.forEach(function(r) {{
    var titleCell = r.doi_url
      ? '<a href="' + r.doi_url + '" target="_blank" rel="noopener">' + escHtml(r.title) + '</a>'
      : escHtml(r.title);
    var topicsBadges = r.topics ? r.topics.split(', ').filter(Boolean)
      .map(function(t) {{ return '<span class="badge">' + escHtml(t) + '</span>'; }}).join('') : '';
    html += '<tr data-search="' + escAttr(r.title + ' ' + r.doi) + '">';
    html += '<td class="title-cell">' + titleCell + '</td>';
    html += '<td>' + (r.year || '') + '</td>';
    html += '<td>' + (r.cited || 0).toLocaleString() + '</td>';
    html += '<td>' + topicsBadges + '</td>';
    html += '</tr>';
  }});
  tbody.innerHTML = html;
}}

function escHtml(s) {{
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}}
function escAttr(s) {{
  return String(s).replace(/"/g,'&quot;').toLowerCase();
}}

function getSortKey(r, col) {{
  if (col === 0) return (r.title || '').toLowerCase();
  if (col === 1) return r.year || 0;
  if (col === 2) return r.cited || 0;
  if (col === 3) return (r.topics || '').toLowerCase();
  return '';
}}

function sortTable(col) {{
  if (sortCol === col) {{ sortAsc = !sortAsc; }} else {{ sortCol = col; sortAsc = true; }}
  var ths = document.querySelectorAll('thead th');
  ths.forEach(function(th, i) {{ th.classList.toggle('sorted', i === col); }});
  var sorted = ROWS.slice().sort(function(a, b) {{
    var ka = getSortKey(a, col), kb = getSortKey(b, col);
    if (ka < kb) return sortAsc ? -1 : 1;
    if (ka > kb) return sortAsc ? 1 : -1;
    return 0;
  }});
  applyFilter(sorted);
}}

function applyFilter(data) {{
  var q = document.getElementById('filterInput').value.toLowerCase();
  var src = data || ROWS;
  var filtered = q ? src.filter(function(r) {{
    return (r.title + ' ' + r.doi).toLowerCase().indexOf(q) !== -1;
  }}) : src;
  renderRows(filtered);
}}

// Initial render sorted by year desc
ROWS.sort(function(a, b) {{ return (b.year || 0) - (a.year || 0); }});
renderRows(ROWS);
</script>"""

    html = _html_shell(f'{label} — PaperSift', 'overview', extra_css, body)
    Path(output_path).write_text(html, encoding='utf-8')
    return output_path
