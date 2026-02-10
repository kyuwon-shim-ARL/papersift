"""Plotly scatter plot component for paper landscape visualization."""

from dash import html, dcc
from typing import Any, Dict, List


def create_landscape_figure(
    embedding_data: Dict[str, list],
    clusters: Dict[str, Any],
    colors: Dict[Any, str],
    papers: List[Dict[str, Any]],
):
    """Create Plotly scatter figure for paper landscape.

    Args:
        embedding_data: {doi: [x, y]} coordinates
        clusters: {doi: cluster_id}
        colors: {cluster_id: hex_color}
        papers: paper list for hover info

    Returns:
        plotly Figure
    """
    import plotly.graph_objects as go

    doi_to_paper = {p['doi']: p for p in papers}

    # Group DOIs by cluster
    cluster_dois = {}
    for doi, cid in clusters.items():
        cluster_dois.setdefault(cid, []).append(doi)

    fig = go.Figure()
    for cid in sorted(cluster_dois.keys(), key=str):
        dois = cluster_dois[cid]
        xs = [embedding_data[d][0] for d in dois if d in embedding_data]
        ys = [embedding_data[d][1] for d in dois if d in embedding_data]
        titles = [doi_to_paper.get(d, {}).get('title', d)[:60] for d in dois if d in embedding_data]
        hover = [f"<b>{t}</b><br>Cluster: {cid}" for t in titles]
        valid_dois = [d for d in dois if d in embedding_data]

        fig.add_trace(go.Scatter(
            x=xs, y=ys,
            mode='markers',
            marker=dict(size=8, color=colors.get(cid, '#cccccc')),
            name=f'Cluster {cid} ({len(dois)})',
            text=hover,
            hoverinfo='text',
            customdata=valid_dois,
        ))

    fig.update_layout(
        xaxis=dict(showticklabels=False, title=''),
        yaxis=dict(showticklabels=False, title=''),
        hovermode='closest',
        template='plotly_white',
        clickmode='event+select',
        dragmode='select',
        margin=dict(l=10, r=10, t=10, b=10),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
    )

    return fig


def create_landscape_component(
    embedding_data: Dict[str, list],
    clusters: Dict[str, Any],
    colors: Dict[Any, str],
    papers: List[Dict[str, Any]],
) -> html.Div:
    """Create Dash component containing the landscape scatter plot.

    Args:
        embedding_data: {doi: [x, y]} coordinates
        clusters: {doi: cluster_id}
        colors: {cluster_id: hex_color}
        papers: paper list for hover info

    Returns:
        html.Div with dcc.Graph
    """
    fig = create_landscape_figure(embedding_data, clusters, colors, papers)

    return html.Div(
        id='landscape-container',
        children=[
            dcc.Graph(
                id='landscape-scatter',
                figure=fig,
                config={'displayModeBar': True, 'scrollZoom': True},
                style={'height': '600px'},
            ),
        ]
    )
