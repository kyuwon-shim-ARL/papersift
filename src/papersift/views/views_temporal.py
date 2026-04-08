"""Timeline (V6) HTML view generator."""

import json
from pathlib import Path
from typing import Any, Dict, List

from .base import (CLUSTER_COLORS, _html_shell)


def generate_timeline(
    temporal: Dict[str, Any],
    labels: Dict[int, str],
    output_path: str,
) -> str:
    """Generate V6: entity trend line chart with toggle checkboxes.

    Args:
        temporal: temporal.json content
        labels: cluster_id -> label string
        output_path: destination file path

    Returns:
        output_path
    """
    cluster_data = temporal.get('clusters', {})

    if not cluster_data:
        body = '<h1>Entity Timeline</h1><p style="color:var(--text2);margin-top:24px;">No temporal data available.</p>'
        html = _html_shell('Entity Timeline — PaperSift', 'timeline', '', body)
        Path(output_path).write_text(html, encoding='utf-8')
        return output_path

    # Collect entities from top_rising/top_declining (or entities fallback)
    all_rising: List[Dict[str, Any]] = []
    all_declining: List[Dict[str, Any]] = []
    cluster_year_ranges: Dict[str, str] = {}
    for cid_str, cdata in cluster_data.items():
        cluster_year_ranges[cid_str] = cdata.get('year_range', '2000-2024')
        # Support both formats: entities[] or top_rising[]/top_declining[]
        if 'entities' in cdata and cdata['entities']:
            for ent in cdata['entities']:
                ent['_cluster_id'] = cid_str
                if ent.get('slope', 0) >= 0:
                    all_rising.append(ent)
                else:
                    all_declining.append(ent)
        else:
            for ent in cdata.get('top_rising', []):
                ent['_cluster_id'] = cid_str
                ent['_direction'] = 'rising'
                all_rising.append(ent)
            for ent in cdata.get('top_declining', []):
                ent['_cluster_id'] = cid_str
                ent['_direction'] = 'declining'
                all_declining.append(ent)

    # Take top entities: rising sorted by slope desc, declining by slope asc
    rising_sorted = sorted(all_rising, key=lambda e: e.get('slope', 0), reverse=True)[:7]
    declining_sorted = sorted(all_declining, key=lambda e: e.get('slope', 0))[:3]
    top_entities = rising_sorted + declining_sorted

    # Build traces with synthetic trend lines
    traces = []
    for i, ent in enumerate(top_entities):
        entity_name = ent.get('entity', f'Entity {i}')
        slope = ent.get('slope', 0)
        cid_str = ent.get('_cluster_id', '0')
        try:
            cid_int = int(cid_str)
        except ValueError:
            cid_int = 0

        # Parse year_range: could be "1995-2023" string or [1995, 2023] list
        yr = cluster_year_ranges.get(cid_str, '2000-2024')
        if isinstance(yr, str) and '-' in yr:
            parts = yr.split('-')
            y_start, y_end = int(parts[0]), int(parts[1])
        elif isinstance(yr, list) and len(yr) == 2:
            y_start, y_end = int(yr[0]), int(yr[1])
        else:
            y_start, y_end = 2000, 2024

        years = list(range(y_start, y_end + 1))
        n_years = max(len(years), 1)
        # Use cluster n_papers for baseline, default 50
        cdata_ref = cluster_data.get(cid_str, {})
        n_papers = cdata_ref.get('n_papers', 50)
        mid = n_papers / n_years
        counts = [max(0, mid + slope * (y - (y_start + y_end) / 2)) for y in years]

        # Significance from q_value (Benjamini-Hochberg corrected p-value)
        is_sig = ent.get('q_value', 1.0) < 0.05
        color = CLUSTER_COLORS[cid_int % len(CLUSTER_COLORS)]
        line_width = 3 if is_sig else 1.5
        dash = 'solid' if is_sig else 'dot'

        traces.append({
            'type': 'scatter',
            'x': years,
            'y': counts,
            'mode': 'lines+markers',
            'name': entity_name + (' *' if is_sig else ''),
            'line': {'color': color, 'width': line_width, 'dash': dash},
            'marker': {'size': 5},
            'hovertemplate': f'{entity_name}<br>Year: %{{x}}<br>Est. papers: %{{y:.1f}}<extra></extra>',
        })

    layout = {
        'margin': {'t': 30, 'l': 50, 'r': 20, 'b': 50},
        'paper_bgcolor': 'rgba(0,0,0,0)',
        'plot_bgcolor': 'rgba(0,0,0,0)',
        'legend': {'orientation': 'v', 'x': 1.02, 'y': 1},
        'xaxis': {'title': 'Year', 'gridcolor': 'rgba(150,150,150,0.15)'},
        'yaxis': {'title': 'Estimated Paper Count', 'gridcolor': 'rgba(150,150,150,0.15)'},
        'font': {'family': '-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif'},
    }

    extra_css = """
.legend-note { font-size:0.85rem; color:var(--text2); margin-bottom:12px; }
"""

    body = f"""<h1>Entity Timeline</h1>
<h2>Top 10 entities by trend significance — * marks statistically significant trends</h2>
<p class="legend-note">Solid lines = significant trend (p &lt; 0.05) &nbsp;|&nbsp; Dotted = non-significant</p>
<div id="chart" class="chart-wrap"></div>
<script>
var TRACES = {json.dumps(traces)};
var LAYOUT = {json.dumps(layout)};
Plotly.newPlot('chart', TRACES, LAYOUT, {{responsive: true, displayModeBar: false}});
function onThemeChange(theme) {{
  var fc = theme === 'dark' ? '#e8e8e8' : '#212529';
  var gc = theme === 'dark' ? 'rgba(200,200,200,0.1)' : 'rgba(100,100,100,0.15)';
  Plotly.relayout('chart', {{
    'font.color': fc,
    'xaxis.gridcolor': gc,
    'yaxis.gridcolor': gc,
    'xaxis.color': fc,
    'yaxis.color': fc,
  }});
}}
</script>"""

    html = _html_shell('Entity Timeline — PaperSift', 'timeline', extra_css, body)
    Path(output_path).write_text(html, encoding='utf-8')
    return output_path
