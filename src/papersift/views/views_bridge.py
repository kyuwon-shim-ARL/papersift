"""Bridge (V3) and ranking (T1) HTML view generators."""

import json
from pathlib import Path
from typing import Any, Dict, List

from .base import (CLUSTER_COLORS, _html_shell)


def generate_bridges(
    gaps: Dict[str, Any],
    labels: Dict[int, str],
    output_path: str,
) -> str:
    """Generate V3: Sankey diagram of cross-cluster bridges.

    Args:
        gaps: gaps.json content with cross_cluster_bridges list
        labels: cluster_id -> label string
        output_path: destination file path

    Returns:
        output_path
    """
    bridges = gaps.get('cross_cluster_bridges', [])

    if not bridges:
        body = '<h1>Cluster Bridges</h1><p style="color:var(--text2);margin-top:24px;">No bridge data available.</p>'
        html = _html_shell('Cluster Bridges — PaperSift', 'bridges', '', body)
        Path(output_path).write_text(html, encoding='utf-8')
        return output_path

    # Collect unique cluster IDs in bridge order
    cluster_ids_seen: List[int] = []
    seen_set: set = set()
    for b in bridges:
        for key in ('cluster_a', 'cluster_b'):
            cid = b[key]
            if cid not in seen_set:
                cluster_ids_seen.append(cid)
                seen_set.add(cid)

    node_index = {cid: i for i, cid in enumerate(cluster_ids_seen)}
    node_labels = [labels.get(cid, f'Cluster {cid}') for cid in cluster_ids_seen]
    node_colors = [CLUSTER_COLORS[i % len(CLUSTER_COLORS)] for i in range(len(cluster_ids_seen))]

    sources, targets, values, link_colors, customdata = [], [], [], [], []
    max_jaccard = max((b.get('entity_jaccard', 0) for b in bridges), default=1) or 1

    for b in bridges:
        ca, cb = b.get('cluster_a'), b.get('cluster_b')
        jaccard = b.get('entity_jaccard', 0)
        shared = b.get('shared_entities', [])
        if ca not in node_index or cb not in node_index:
            continue
        sources.append(node_index[ca])
        targets.append(node_index[cb])
        values.append(max(jaccard * 100, 1))  # scale for visibility
        alpha = 0.3 + 0.5 * (jaccard / max_jaccard)
        link_colors.append(f'rgba(52, 152, 219, {alpha:.2f})')
        customdata.append(f"Jaccard: {jaccard:.3f} | Shared: {', '.join(shared[:5])}")

    sankey_data = {
        'type': 'sankey',
        'node': {
            'label': node_labels,
            'color': node_colors,
            'pad': 20,
            'thickness': 20,
        },
        'link': {
            'source': sources,
            'target': targets,
            'value': values,
            'color': link_colors,
            'customdata': customdata,
            'hovertemplate': '%{customdata}<extra></extra>',
        },
    }

    layout = {
        'margin': {'t': 20, 'l': 20, 'r': 20, 'b': 20},
        'paper_bgcolor': 'rgba(0,0,0,0)',
        'plot_bgcolor': 'rgba(0,0,0,0)',
        'font': {'family': '-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif', 'size': 12},
    }

    # V10: Bridge evaluation data for JS
    bridge_eval_data = json.dumps([
        {
            'id': f"{b.get('cluster_a', 0)}_{b.get('cluster_b', 0)}",
            'label_a': labels.get(b.get('cluster_a', 0), f"C{b.get('cluster_a', 0)}"),
            'label_b': labels.get(b.get('cluster_b', 0), f"C{b.get('cluster_b', 0)}"),
            'jaccard': round(b.get('entity_jaccard', 0), 3),
            'shared': b.get('shared_entities', [])[:5],
        }
        for b in bridges[:20]  # top 20 bridges
    ])

    extra_css = """
.eval-panel { margin-top:24px; padding:18px 20px; border:1px solid var(--border); border-radius:10px; background:var(--card-bg); }
.eval-panel h3 { margin:0 0 12px 0; font-size:1.05rem; }
.eval-table { width:100%; border-collapse:collapse; font-size:0.88rem; }
.eval-table th { text-align:left; padding:8px 6px; border-bottom:2px solid var(--border); font-weight:600; }
.eval-table td { padding:6px; border-bottom:1px solid var(--border); vertical-align:middle; }
.eval-table tr:hover { background:var(--hover-bg); }
.eval-slider { width:80px; accent-color:#3498db; vertical-align:middle; }
.eval-val { display:inline-block; width:20px; text-align:center; font-size:0.8rem; color:var(--text2); }
.eval-actions { margin-top:14px; display:flex; gap:10px; align-items:center; }
.eval-btn { padding:7px 16px; border-radius:6px; border:1px solid var(--border); background:var(--card-bg); color:var(--text1); cursor:pointer; font-size:0.85rem; }
.eval-btn:hover { background:var(--hover-bg); }
.eval-btn.primary { background:#3498db; color:#fff; border-color:#3498db; }
.eval-saved { color:#2ecc71; font-size:0.85rem; opacity:0; transition:opacity 0.3s; }
"""

    sankey_json = json.dumps({'data': [sankey_data], 'layout': layout})

    body = f"""<h1>Cluster Bridges</h1>
<h2>Entity overlap between clusters — link width proportional to Jaccard similarity</h2>
<div id="chart" class="chart-wrap"></div>

<!-- V10: Bridge Evaluation -->
<div class="eval-panel">
  <h3>Bridge Evaluation</h3>
  <p style="font-size:0.85rem;color:var(--text2);margin:0 0 10px 0;">Rate each bridge's research potential. Scores persist in your browser.</p>
  <div style="overflow-x:auto;">
    <table class="eval-table">
      <thead><tr>
        <th>Bridge</th><th>Jaccard</th><th>Shared Entities</th>
        <th>Novelty (1-5)</th><th>Feasibility (1-5)</th><th>Interest (1-5)</th><th>Avg</th>
      </tr></thead>
      <tbody id="eval-body"></tbody>
    </table>
  </div>
  <div class="eval-actions">
    <button class="eval-btn primary" onclick="exportEval()">Export JSON</button>
    <button class="eval-btn" onclick="document.getElementById('eval-import').click()">Import JSON</button>
    <input type="file" id="eval-import" accept=".json" style="display:none" onchange="importEval(this)">
    <button class="eval-btn" onclick="clearEval()">Reset All</button>
    <span class="eval-saved" id="eval-saved">Saved!</span>
  </div>
</div>

<script>
var DATA = {sankey_json};
Plotly.newPlot('chart', DATA.data, DATA.layout, {{responsive: true, displayModeBar: false}});
function onThemeChange(theme) {{
  var fc = theme === 'dark' ? '#e8e8e8' : '#212529';
  Plotly.relayout('chart', {{'font.color': fc}});
}}

// V10: Bridge evaluation
var BRIDGES = {bridge_eval_data};
var LS_EVAL = 'papersift_bridge_eval';

function loadEval() {{
  try {{ return JSON.parse(localStorage.getItem(LS_EVAL)) || {{}}; }} catch(e) {{ return {{}}; }}
}}
function saveEval(state) {{
  localStorage.setItem(LS_EVAL, JSON.stringify(state));
  var el = document.getElementById('eval-saved');
  el.style.opacity = '1';
  setTimeout(function() {{ el.style.opacity = '0'; }}, 1200);
}}
function buildEvalTable() {{
  var tbody = document.getElementById('eval-body');
  var state = loadEval();
  BRIDGES.forEach(function(b) {{
    var s = state[b.id] || {{novelty:3, feasibility:3, interest:3}};
    var tr = document.createElement('tr');
    var avg = ((s.novelty + s.feasibility + s.interest) / 3).toFixed(1);
    tr.innerHTML = '<td><strong>' + escHtml(b.label_a) + '</strong> ↔ <strong>' + escHtml(b.label_b) + '</strong></td>'
      + '<td>' + b.jaccard + '</td>'
      + '<td style="font-size:0.8rem;color:var(--text2)">' + b.shared.join(', ') + '</td>'
      + sliderCell(b.id, 'novelty', s.novelty)
      + sliderCell(b.id, 'feasibility', s.feasibility)
      + sliderCell(b.id, 'interest', s.interest)
      + '<td class="avg-cell" id="avg-' + b.id + '">' + avg + '</td>';
    tbody.appendChild(tr);
  }});
}}
function sliderCell(bid, dim, val) {{
  return '<td><input type="range" min="1" max="5" value="' + val + '" class="eval-slider" '
    + 'oninput="onSlider(this,\\x27' + bid + '\\x27,\\x27' + dim + '\\x27)">'
    + '<span class="eval-val" id="v-' + bid + '-' + dim + '">' + val + '</span></td>';
}}
function onSlider(el, bid, dim) {{
  var state = loadEval();
  if (!state[bid]) state[bid] = {{novelty:3, feasibility:3, interest:3}};
  state[bid][dim] = parseInt(el.value);
  document.getElementById('v-' + bid + '-' + dim).textContent = el.value;
  var s = state[bid];
  document.getElementById('avg-' + bid).textContent = ((s.novelty + s.feasibility + s.interest) / 3).toFixed(1);
  saveEval(state);
}}
function exportEval() {{
  var state = loadEval();
  var enriched = BRIDGES.map(function(b) {{
    var s = state[b.id] || {{novelty:3, feasibility:3, interest:3}};
    return {{bridge: b.id, label_a: b.label_a, label_b: b.label_b, jaccard: b.jaccard,
      shared_entities: b.shared, novelty: s.novelty, feasibility: s.feasibility,
      interest: s.interest, avg: +((s.novelty + s.feasibility + s.interest) / 3).toFixed(2)}};
  }});
  var blob = new Blob([JSON.stringify(enriched, null, 2)], {{type:'application/json'}});
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'bridge_evaluation.json';
  a.click();
}}
function clearEval() {{
  if (!confirm('Reset all bridge evaluations?')) return;
  localStorage.removeItem(LS_EVAL);
  document.getElementById('eval-body').innerHTML = '';
  buildEvalTable();
}}
function importEval(input) {{
  if (!input.files.length) return;
  var reader = new FileReader();
  reader.onload = function(e) {{
    try {{
      var raw = JSON.parse(e.target.result);
      var state = {{}};
      if (Array.isArray(raw)) {{
        raw.forEach(function(r) {{
          if (r.bridge) state[r.bridge] = {{novelty: r.novelty||3, feasibility: r.feasibility||3, interest: r.interest||3}};
        }});
      }} else {{
        state = raw;
      }}
      localStorage.setItem(LS_EVAL, JSON.stringify(state));
      document.getElementById('eval-body').innerHTML = '';
      buildEvalTable();
    }} catch(err) {{ alert('Invalid JSON file'); }}
  }};
  reader.readAsText(input.files[0]);
  input.value = '';
}}
buildEvalTable();
</script>"""

    html = _html_shell('Cluster Bridges — PaperSift', 'bridges', extra_css, body)
    Path(output_path).write_text(html, encoding='utf-8')
    return output_path


def generate_ranking(
    gaps: Dict[str, Any],
    labels: Dict[int, str],
    output_path: str,
) -> str:
    """Generate T1: Bridge ranking page sorted by V10 evaluation scores.

    Reads bridge data from gaps.json and renders a client-side ranked table
    that pulls evaluation scores from localStorage (papersift_bridge_eval).

    Args:
        gaps: gaps.json content with cross_cluster_bridges list
        labels: cluster_id -> label string
        output_path: destination file path

    Returns:
        output_path
    """
    bridges = gaps.get('cross_cluster_bridges', [])

    if not bridges:
        body = '<h1>Bridge Ranking</h1><p style="color:var(--text2);margin-top:24px;">No bridge data available. Evaluate bridges first on the Bridges page.</p>'
        html = _html_shell('Bridge Ranking — PaperSift', 'ranking', '', body)
        Path(output_path).write_text(html, encoding='utf-8')
        return output_path

    bridge_data = json.dumps([
        {
            'id': f"{b.get('cluster_a', 0)}_{b.get('cluster_b', 0)}",
            'label_a': labels.get(b.get('cluster_a', 0), f"C{b.get('cluster_a', 0)}"),
            'label_b': labels.get(b.get('cluster_b', 0), f"C{b.get('cluster_b', 0)}"),
            'jaccard': round(b.get('entity_jaccard', 0), 3),
            'shared': b.get('shared_entities', [])[:5],
        }
        for b in bridges[:20]
    ])

    extra_css = """
.rank-panel { padding:18px 20px; border:1px solid var(--border); border-radius:10px; background:var(--card-bg); margin-top:16px; }
.rank-panel h3 { margin:0 0 12px 0; font-size:1.05rem; }
.rank-table { width:100%; border-collapse:collapse; font-size:0.88rem; }
.rank-table th { text-align:left; padding:10px 8px; border-bottom:2px solid var(--border); font-weight:600; cursor:pointer; user-select:none; }
.rank-table th:hover { color:var(--accent); }
.rank-table th.sorted { color:var(--accent); }
.rank-table td { padding:8px; border-bottom:1px solid var(--border); vertical-align:middle; }
.rank-table tr:hover { background:var(--hover-bg); }
.rank-num { font-size:1.1rem; font-weight:700; color:var(--accent); width:40px; text-align:center; }
.score-bar { display:inline-block; height:8px; border-radius:4px; background:var(--accent); vertical-align:middle; margin-right:6px; }
.score-val { font-weight:600; }
.no-eval { color:var(--text2); font-style:italic; font-size:0.85rem; }
.rank-summary { display:flex; gap:20px; flex-wrap:wrap; margin-bottom:20px; }
.rank-stat { background:var(--card-bg); border:1px solid var(--border); border-radius:8px; padding:14px 18px; min-width:140px; }
.rank-stat .stat-value { font-size:1.6rem; font-weight:700; color:var(--accent); }
.rank-stat .stat-label { font-size:0.82rem; color:var(--text2); margin-top:2px; }
"""

    body = f"""<h1>Bridge Ranking</h1>
<h2>Bridges ranked by your evaluation scores — rate them on the Bridges page</h2>

<div class="rank-summary" id="rank-summary"></div>

<div class="rank-panel">
  <h3>Ranked Bridges</h3>
  <div style="overflow-x:auto;">
    <table class="rank-table" id="rank-table">
      <thead><tr>
        <th>#</th>
        <th onclick="sortRank(1)">Bridge</th>
        <th onclick="sortRank(2)">Jaccard</th>
        <th onclick="sortRank(3)">Shared Entities</th>
        <th onclick="sortRank(4)">Novelty</th>
        <th onclick="sortRank(5)">Feasibility</th>
        <th onclick="sortRank(6)">Interest</th>
        <th onclick="sortRank(7)" class="sorted">Avg Score</th>
      </tr></thead>
      <tbody id="rank-body"></tbody>
    </table>
  </div>
</div>

<script>
var BRIDGES = {bridge_data};
var LS_EVAL = 'papersift_bridge_eval';
var sortCol = 7, sortAsc = false;

function loadEval() {{
  try {{ return JSON.parse(localStorage.getItem(LS_EVAL)) || {{}}; }} catch(e) {{ return {{}}; }}
}}

function buildRanking() {{
  var state = loadEval();
  var rows = BRIDGES.map(function(b) {{
    var s = state[b.id] || null;
    var avg = s ? +((s.novelty + s.feasibility + s.interest) / 3).toFixed(2) : 0;
    return {{
      id: b.id, label_a: b.label_a, label_b: b.label_b,
      jaccard: b.jaccard, shared: b.shared,
      novelty: s ? s.novelty : 0,
      feasibility: s ? s.feasibility : 0,
      interest: s ? s.interest : 0,
      avg: avg, evaluated: !!s
    }};
  }});

  // Sort
  rows.sort(function(a, b) {{
    var ka, kb;
    switch(sortCol) {{
      case 1: ka = a.label_a; kb = b.label_a; break;
      case 2: ka = a.jaccard; kb = b.jaccard; break;
      case 3: ka = a.shared.join(''); kb = b.shared.join(''); break;
      case 4: ka = a.novelty; kb = b.novelty; break;
      case 5: ka = a.feasibility; kb = b.feasibility; break;
      case 6: ka = a.interest; kb = b.interest; break;
      default: ka = a.avg; kb = b.avg;
    }}
    if (ka < kb) return sortAsc ? -1 : 1;
    if (ka > kb) return sortAsc ? 1 : -1;
    return 0;
  }});

  // Summary stats
  var evaluated = rows.filter(function(r) {{ return r.evaluated; }});
  var topBridge = evaluated.length ? evaluated.reduce(function(a, b) {{ return a.avg >= b.avg ? a : b; }}) : null;
  var avgAll = evaluated.length ? (evaluated.reduce(function(s, r) {{ return s + r.avg; }}, 0) / evaluated.length).toFixed(1) : '—';
  var summaryHtml = '<div class="rank-stat"><div class="stat-value">' + evaluated.length + '/' + rows.length + '</div><div class="stat-label">Evaluated</div></div>'
    + '<div class="rank-stat"><div class="stat-value">' + avgAll + '</div><div class="stat-label">Avg Score</div></div>';
  if (topBridge) {{
    summaryHtml += '<div class="rank-stat"><div class="stat-value">' + topBridge.avg.toFixed(1) + '</div><div class="stat-label">Top: ' + escHtml(topBridge.label_a) + ' ↔ ' + escHtml(topBridge.label_b) + '</div></div>';
  }}
  document.getElementById('rank-summary').innerHTML = summaryHtml;

  // Table
  var tbody = document.getElementById('rank-body');
  var html = '';
  rows.forEach(function(r, i) {{
    var barW = Math.round(r.avg / 5 * 100);
    var scoreHtml = r.evaluated
      ? '<span class="score-bar" style="width:' + barW + 'px"></span><span class="score-val">' + r.avg.toFixed(1) + '</span>'
      : '<span class="no-eval">Not rated</span>';
    var dimHtml = function(v) {{ return r.evaluated ? v : '—'; }};
    html += '<tr>'
      + '<td class="rank-num">' + (i + 1) + '</td>'
      + '<td><strong>' + escHtml(r.label_a) + '</strong> ↔ <strong>' + escHtml(r.label_b) + '</strong></td>'
      + '<td>' + r.jaccard + '</td>'
      + '<td style="font-size:0.8rem;color:var(--text2)">' + r.shared.join(', ') + '</td>'
      + '<td>' + dimHtml(r.novelty) + '</td>'
      + '<td>' + dimHtml(r.feasibility) + '</td>'
      + '<td>' + dimHtml(r.interest) + '</td>'
      + '<td>' + scoreHtml + '</td>'
      + '</tr>';
  }});
  tbody.innerHTML = html;
}}

function sortRank(col) {{
  var ths = document.querySelectorAll('.rank-table th');
  if (sortCol === col) {{ sortAsc = !sortAsc; }} else {{ sortCol = col; sortAsc = col <= 3; }}
  ths.forEach(function(th, i) {{ th.classList.toggle('sorted', i === col); }});
  buildRanking();
}}

buildRanking();
// Refresh when returning from bridges page (evaluation may have changed)
window.addEventListener('focus', buildRanking);
</script>"""

    html = _html_shell('Bridge Ranking — PaperSift', 'ranking', extra_css, body)
    Path(output_path).write_text(html, encoding='utf-8')
    return output_path
