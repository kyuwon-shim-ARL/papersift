"""Analysis tab components: Methods, Gaps, Hypotheses."""

import json
from pathlib import Path
from typing import Any, Dict, Optional

from dash import html, dcc
import plotly.graph_objects as go


def _load_json(path: Path) -> Optional[dict]:
    """Load JSON file, returning None if not found."""
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _no_data_message(name: str) -> html.Div:
    """Return a 'no data available' placeholder."""
    return html.Div([
        html.P(f'No {name} data available.', style={
            'textAlign': 'center', 'color': 'var(--text-secondary)',
            'padding': '60px 20px', 'fontSize': '16px',
        }),
        html.P('Run the analysis pipeline first: papersift research <papers.json>', style={
            'textAlign': 'center', 'color': 'var(--text-secondary)',
            'fontSize': '13px',
        }),
    ])


# ---------------------------------------------------------------------------
# Method name mapping (abbreviated <-> full)
# ---------------------------------------------------------------------------
ABBREV_TO_FULL = {
    "ABM": "Agent-based model", "ML/DL": "Machine learning / Deep learning",
    "docking/VS": "Docking / Virtual screening", "FEM": "Finite element / FEM",
    "GRN": "Gene regulatory network", "PK/PBPK": "Pharmacokinetic / PK",
    "stochastic": "Stochastic simulation", "multiscale": "Multiscale modeling",
    "whole-cell": "Whole-cell model", "systems biology": "Systems biology",
    "molecular dynamics": "Molecular dynamics", "FBA": "FBA / Flux balance",
    "Boolean": "Boolean network", "QSAR": "QSAR / QSPR",
    "constraint-based": "Constraint-based", "ODE": "ODE", "PDE": "PDE",
    "Bayesian": "Bayesian", "Markov": "Markov", "Monte Carlo": "Monte Carlo",
    "single-cell/scRNA": "single-cell/scRNA", "digital twin": "digital twin",
}


def _hex_to_rgba(hex_color: str, alpha: float = 0.25) -> str:
    """Convert hex color to rgba string for Plotly."""
    h = hex_color.lstrip('#')
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f'rgba({r},{g},{b},{alpha})'


def create_sankey_figure(method_flows: dict, trend_data: dict) -> go.Figure:
    """Create Sankey flow diagram: Methods -> Clusters."""
    flows = method_flows.get('method_flows', {})
    if not flows:
        return go.Figure()

    # Get top 8 methods by paper count
    sorted_methods = sorted(flows.items(), key=lambda x: x[1].get('total_papers', 0), reverse=True)[:8]
    method_names = [m[0] for m in sorted_methods]

    # Collect all cluster IDs
    cluster_ids = set()
    for _, info in sorted_methods:
        cluster_ids.update(info.get('cluster_distribution', {}).keys())
    cluster_ids = sorted(cluster_ids)

    # Build cluster labels from metadata
    bio_clusters = method_flows.get('metadata', {}).get('biology_clusters', {})
    cluster_labels = [bio_clusters.get(c, c) for c in cluster_ids]

    # Build nodes: methods first, then clusters
    nodes = method_names + cluster_labels
    sources, targets, values = [], [], []

    for mi, (method, info) in enumerate(sorted_methods):
        dist = info.get('cluster_distribution', {})
        for ci, cid in enumerate(cluster_ids):
            count = dist.get(cid, 0)
            if count > 0:
                sources.append(mi)
                targets.append(len(method_names) + ci)
                values.append(count)

    method_colors = ['#95a5a6', '#7f8c8d', '#bdc3c7', '#85929e',
                     '#aab7b8', '#a3b1bf', '#99a3ad', '#8e979f']
    domain_colors = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6',
                     '#1abc9c', '#e67e22', '#34495e']

    node_colors = [method_colors[i % len(method_colors)] for i in range(len(method_names))]
    node_colors += [domain_colors[i % len(domain_colors)] for i in range(len(cluster_ids))]

    link_colors = []
    for t in targets:
        ci = t - len(method_names)
        c = domain_colors[ci % len(domain_colors)] if ci >= 0 else '#cccccc'
        link_colors.append(_hex_to_rgba(c, 0.25))

    fig = go.Figure(go.Sankey(
        orientation='h',
        node=dict(pad=15, thickness=20, line=dict(color='rgba(0,0,0,0.2)', width=0.5),
                  label=nodes, color=node_colors),
        link=dict(source=sources, target=targets, value=values, color=link_colors),
    ))
    fig.update_layout(
        margin=dict(t=10, l=10, r=10, b=10),
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(size=11),
        height=400,
    )
    return fig


def create_temporal_figure(trend_data: dict) -> go.Figure:
    """Create stacked area chart of method evolution over time."""
    temporal = trend_data.get('task2_temporal_evolution', {})
    if not temporal:
        return go.Figure()

    periods = sorted(temporal.keys())

    # Collect all methods and their counts per period
    # Structure: {period: {total_papers: int, methods: {method: count}}} or {period: {method: count}}
    method_totals = {}
    for period in periods:
        period_data = temporal[period]
        methods_dict = period_data.get('methods', period_data) if isinstance(period_data, dict) else {}
        for method, count in methods_dict.items():
            if method == 'total_papers':
                continue
            if isinstance(count, (int, float)):
                method_totals[method] = method_totals.get(method, 0) + count

    # Top 8 methods
    top_methods = sorted(method_totals.items(), key=lambda x: x[1], reverse=True)[:8]
    top_method_names = [m[0] for m in top_methods]

    colors = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6',
              '#1abc9c', '#e67e22', '#34495e']

    fig = go.Figure()
    for i, method in enumerate(top_method_names):
        y_vals = []
        for p in periods:
            period_data = temporal.get(p, {})
            methods_dict = period_data.get('methods', period_data) if isinstance(period_data, dict) else {}
            y_vals.append(methods_dict.get(method, 0) if isinstance(methods_dict, dict) else 0)
        fig.add_trace(go.Scatter(
            x=periods, y=y_vals, name=method,
            mode='lines', stackgroup='one',
            fillcolor=_hex_to_rgba(colors[i % len(colors)], 0.5),
            line=dict(color=colors[i % len(colors)], width=1),
        ))

    fig.update_layout(
        margin=dict(t=10, l=50, r=10, b=40),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        yaxis=dict(title='Papers', gridcolor='rgba(128,128,128,0.2)'),
        xaxis=dict(gridcolor='rgba(128,128,128,0.2)'),
        font=dict(size=11),
        legend=dict(orientation='h', y=-0.15),
        hovermode='x unified',
        height=350,
    )
    return fig


def create_heatmap_figure(trend_data: dict) -> go.Figure:
    """Create Problem x Method heatmap from trend analysis."""
    matrix = trend_data.get('task5_problem_method_matrix', {})
    if not matrix:
        return go.Figure()

    problems = list(matrix.keys())
    # Collect all methods across all problems
    all_methods = set()
    for p_methods in matrix.values():
        all_methods.update(p_methods.keys())

    # Sort methods by total count
    method_totals = {}
    for p, methods in matrix.items():
        for m, count in methods.items():
            method_totals[m] = method_totals.get(m, 0) + count
    methods = sorted(method_totals.keys(), key=lambda m: method_totals[m], reverse=True)[:12]

    z = []
    for p in problems:
        row = [matrix[p].get(m, 0) for m in methods]
        z.append(row)

    fig = go.Figure(go.Heatmap(
        z=z, x=methods, y=problems,
        colorscale=[
            [0, '#f8f9fa'], [0.01, '#fff3cd'], [0.1, '#ffc107'],
            [0.3, '#fd7e14'], [0.6, '#dc3545'], [1, '#7b2d26'],
        ],
        hoverongaps=False,
        hovertemplate='%{y}<br>%{x}<br>Papers: %{z}<extra></extra>',
    ))
    fig.update_layout(
        margin=dict(t=10, l=200, r=20, b=80),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(tickangle=-45),
        font=dict(size=11),
        height=450,
    )
    return fig


def _create_hypothesis_cards(hypotheses_data: dict) -> html.Div:
    """Create hypothesis cards from JSON data."""
    hypotheses = hypotheses_data.get('hypotheses', [])
    if not hypotheses:
        return _no_data_message('hypothesis')

    conf_colors = {'High': '#28a745', 'Medium': '#ffc107', 'Low': '#dc3545'}

    cards = []
    for h in hypotheses:
        conf = h.get('confidence', 'Medium')
        dois = h.get('supporting_dois', [])

        card_children = [
            html.Div([
                html.Span(h.get('id', ''), style={
                    'fontWeight': 'bold', 'marginRight': '10px',
                    'color': 'var(--accent)',
                }),
                html.Span(conf, style={
                    'padding': '2px 8px', 'borderRadius': '12px',
                    'fontSize': '12px', 'color': 'white',
                    'backgroundColor': conf_colors.get(conf, '#6c757d'),
                }),
            ], style={'marginBottom': '8px'}),
            html.H4(h.get('title', ''), style={
                'margin': '0 0 8px 0', 'fontSize': '15px',
            }),
            html.P(h.get('hypothesis', '')[:200] + '...' if len(h.get('hypothesis', '')) > 200 else h.get('hypothesis', ''),
                   style={'fontSize': '13px', 'lineHeight': '1.5', 'color': 'var(--text-secondary)'}),
            html.Details([
                html.Summary('Evidence & Impact', style={'cursor': 'pointer', 'fontSize': '13px', 'color': 'var(--accent)'}),
                html.P([html.Strong('Evidence: '), h.get('evidence', 'N/A')],
                       style={'fontSize': '12px', 'marginTop': '5px'}),
                html.P([html.Strong('Impact: '), h.get('impact', 'N/A')],
                       style={'fontSize': '12px', 'marginTop': '5px'}),
            ]),
        ]

        # Add "Show Papers" button if supporting_dois exist
        if dois:
            card_children.append(
                html.Button(
                    f'Show {len(dois)} supporting papers',
                    id={'type': 'hyp-select-btn', 'index': h.get('id', '')},
                    n_clicks=0,
                    style={
                        'marginTop': '8px', 'padding': '5px 12px', 'borderRadius': '12px',
                        'border': '1px solid var(--accent)', 'cursor': 'pointer',
                        'backgroundColor': 'transparent', 'color': 'var(--accent)',
                        'fontSize': '12px',
                    },
                )
            )

        cards.append(html.Div(card_children, style={
            'padding': '15px', 'marginBottom': '12px',
            'borderRadius': '8px', 'border': '1px solid var(--border-color)',
            'backgroundColor': 'var(--bg-card)',
        }))

    return html.Div(cards)


def _create_gap_cards(hypotheses_data: dict) -> html.Div:
    """Create gap analysis cards."""
    gaps = hypotheses_data.get('gap_analysis', {}).get('white_spaces_top20', [])
    if not gaps:
        return _no_data_message('gap analysis')

    cards = []
    for g in gaps[:10]:
        score = g.get('opportunity_score', 0)
        cards.append(html.Div([
            html.Div([
                html.Span(f"{g.get('problem', '')} + {g.get('method', '')}",
                          style={'fontWeight': 'bold', 'fontSize': '14px'}),
                html.Span(f'Score: {score:,}', style={
                    'fontSize': '12px', 'color': 'var(--text-secondary)', 'marginLeft': '10px',
                }),
            ]),
            html.Div([
                html.Span(f"Problem papers: {g.get('problem_papers', 0)}", style={'fontSize': '12px', 'marginRight': '15px'}),
                html.Span(f"Method papers: {g.get('method_papers', 0)}", style={'fontSize': '12px'}),
            ], style={'marginTop': '5px', 'color': 'var(--text-secondary)'}),
        ], style={
            'padding': '12px', 'marginBottom': '8px',
            'borderRadius': '6px', 'border': '1px solid var(--border-color)',
            'backgroundColor': 'var(--bg-card)',
        }))

    return html.Div(cards)


def load_analysis_data(analysis_dir: str) -> Dict[str, Any]:
    """Load all analysis JSON files from a directory."""
    d = Path(analysis_dir)
    return {
        'method_flows': _load_json(d / 'method_flows.json'),
        'trend_analysis': _load_json(d / 'trend_analysis.json'),
        'hypotheses': _load_json(d / 'hypotheses.json'),
        'landscape_map': _load_json(d / 'landscape_map.json'),
    }


def create_analysis_component(analysis_data: Dict[str, Any]) -> html.Div:
    """Create the full analysis tab content with sub-tabs."""
    method_flows = analysis_data.get('method_flows')
    trend_data = analysis_data.get('trend_analysis')
    hypotheses_data = analysis_data.get('hypotheses')

    has_data = any(v is not None for v in [method_flows, trend_data, hypotheses_data])

    if not has_data:
        return _no_data_message('analysis')

    # Methods sub-tab
    methods_content = []
    if method_flows and trend_data:
        methods_content = [
            html.H3('Method Flow: Top Methods across Clusters', style={'marginBottom': '10px'}),
            dcc.Graph(
                id='analysis-sankey',
                figure=create_sankey_figure(method_flows, trend_data),
                config={'displayModeBar': False},
                style={'width': '100%'},
            ),
            html.Hr(style={'borderColor': 'var(--border-color)'}),
            html.H3('Temporal Evolution of Methods', style={'marginBottom': '10px'}),
            dcc.Graph(
                id='analysis-temporal',
                figure=create_temporal_figure(trend_data),
                config={'displayModeBar': True, 'displaylogo': False},
                style={'width': '100%'},
            ),
        ]
    else:
        methods_content = [_no_data_message('method flow')]

    # Gaps sub-tab
    gaps_content = []
    if trend_data:
        gaps_content.append(html.H3('Problem x Method Matrix', style={'marginBottom': '10px'}))
        gaps_content.append(
            dcc.Graph(
                id='analysis-heatmap',
                figure=create_heatmap_figure(trend_data),
                config={'displayModeBar': True, 'displaylogo': False},
                style={'width': '100%'},
            )
        )
    if hypotheses_data:
        gaps_content.append(html.Hr(style={'borderColor': 'var(--border-color)'}))
        gaps_content.append(html.H3('Research Gaps (White Spaces)', style={'marginBottom': '10px'}))
        gaps_content.append(_create_gap_cards(hypotheses_data))
    if not gaps_content:
        gaps_content = [_no_data_message('gap analysis')]

    # Hypotheses sub-tab
    hyp_content = []
    if hypotheses_data:
        hyp_content = [
            html.H3('Research Hypotheses', style={'marginBottom': '10px'}),
            _create_hypothesis_cards(hypotheses_data),
        ]
    else:
        hyp_content = [_no_data_message('hypotheses')]

    return html.Div([
        # Store analysis data for callbacks
        dcc.Store(id='analysis-method-flows', data=method_flows),
        dcc.Store(id='analysis-trend-data', data=trend_data),
        dcc.Store(id='analysis-hypotheses', data=hypotheses_data),

        dcc.Tabs(id='analysis-subtabs', value='methods-subtab', children=[
            dcc.Tab(label='Methods', value='methods-subtab', children=[
                html.Div(methods_content, style={'padding': '15px'}),
            ]),
            dcc.Tab(label='Gaps', value='gaps-subtab', children=[
                html.Div(gaps_content, style={'padding': '15px'}),
            ]),
            dcc.Tab(label='Hypotheses', value='hypotheses-subtab', children=[
                html.Div(hyp_content, style={'padding': '15px'}),
            ]),
        ]),
    ])
