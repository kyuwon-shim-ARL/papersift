"""Plotly scatter plot component for paper landscape visualization."""

from dash import html, dcc
from typing import Any, Dict, List
import numpy as np

try:
    from scipy.spatial import ConvexHull
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False


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

    # Draw contours first (so points appear on top)
    if HAS_SCIPY:
        for cid in sorted(cluster_dois.keys(), key=str):
            dois = cluster_dois[cid]
            points = [[embedding_data[d][0], embedding_data[d][1]] for d in dois if d in embedding_data]
            if len(points) >= 3:
                pts = np.array(points)
                try:
                    hull = ConvexHull(pts)
                    hull_x = [pts[v, 0] for v in hull.vertices] + [pts[hull.vertices[0], 0]]
                    hull_y = [pts[v, 1] for v in hull.vertices] + [pts[hull.vertices[0], 1]]

                    # Convert rgb to rgba with 0.1 opacity
                    color = colors.get(cid, '#cccccc')
                    if color.startswith('rgb('):
                        fillcolor = color.replace('rgb(', 'rgba(').replace(')', ',0.1)')
                    elif color.startswith('#'):
                        # Convert hex to rgba
                        h = color.lstrip('#')
                        r, g, b = tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
                        fillcolor = f'rgba({r},{g},{b},0.1)'
                    else:
                        fillcolor = 'rgba(200,200,200,0.1)'

                    fig.add_trace(go.Scatter(
                        x=hull_x, y=hull_y,
                        fill='toself',
                        fillcolor=fillcolor,
                        line=dict(color=color, width=1, dash='dot'),
                        showlegend=False,
                        hoverinfo='skip',
                        mode='lines',
                    ))
                except Exception:
                    pass  # Skip if hull fails (e.g., collinear points)

    # Draw scatter points
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

    # Add cluster label annotations at centroids
    for cid in sorted(cluster_dois.keys(), key=str):
        dois = cluster_dois[cid]
        cxs = [embedding_data[d][0] for d in dois if d in embedding_data]
        cys = [embedding_data[d][1] for d in dois if d in embedding_data]
        if cxs:
            cx = sum(cxs) / len(cxs)
            cy = sum(cys) / len(cys)
            fig.add_annotation(
                x=cx, y=cy,
                text=f'C{cid}',
                showarrow=False,
                font=dict(size=14, color='rgba(0,0,0,0.6)'),
                bgcolor='rgba(255,255,255,0.7)',
                borderpad=3,
            )

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
