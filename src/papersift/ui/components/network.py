"""Cluster Bubble Chart visualization component (replaces Cytoscape network)."""

from dash import html, dcc
import plotly.graph_objects as go
from typing import Any, Dict, List
import math


def create_bubble_figure(
    embedding_data: Dict[str, list],
    clusters: Dict[str, Any],
    colors: Dict[Any, str],
    papers: List[Dict[str, Any]],
) -> go.Figure:
    """Create Plotly bubble chart showing cluster centroids."""

    # Calculate cluster centroids and sizes
    cluster_points = {}
    for doi, cid in clusters.items():
        if doi in embedding_data:
            cluster_points.setdefault(cid, []).append(embedding_data[doi])

    # Build DOI to paper lookup
    paper_by_doi = {p.get('doi'): p for p in papers if p.get('doi')}

    fig = go.Figure()

    for cid in sorted(cluster_points.keys(), key=str):
        points = cluster_points[cid]
        cx = sum(p[0] for p in points) / len(points)
        cy = sum(p[1] for p in points) / len(points)
        size = max(20, math.sqrt(len(points)) * 8)  # Scale bubble size

        # Collect DOIs and papers for this cluster
        cluster_dois = [doi for doi, c in clusters.items() if c == cid]
        cluster_papers = [paper_by_doi[doi] for doi in cluster_dois if doi in paper_by_doi]

        # Calculate year range
        years = [p.get('year') for p in cluster_papers if p.get('year')]
        year_range = f"{min(years)}-{max(years)}" if years else "N/A"

        # Calculate top 3 topics
        topic_counts = {}
        for paper in cluster_papers:
            topics = paper.get('topics', [])
            for topic in topics[:3]:  # Only consider top 3 topics per paper
                name = topic.get('display_name') if isinstance(topic, dict) else str(topic)
                topic_counts[name] = topic_counts.get(name, 0) + 1

        top_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:3]
        topics_str = ', '.join([t[0] for t in top_topics]) if top_topics else 'N/A'

        # Get 2 most recent representative papers
        recent_papers = sorted(
            [p for p in cluster_papers if p.get('year')],
            key=lambda x: x.get('year', 0),
            reverse=True
        )[:2]

        papers_str = ''
        for paper in recent_papers:
            title = paper.get('title', 'Untitled')
            # Truncate to 50 chars
            if len(title) > 50:
                title = title[:47] + '...'
            year = paper.get('year', '')
            papers_str += f'• "{title}" ({year})<br>'

        # Build rich hover template
        hover_text = (
            f'<b>Cluster {cid} ({len(points)} papers)</b><br>'
            f'Years: {year_range}<br>'
            f'Topics: {topics_str}<br>'
            f'{papers_str}'
            '<extra></extra>'
        )

        fig.add_trace(go.Scatter(
            x=[cx], y=[cy],
            mode='markers+text',
            marker=dict(
                size=size,
                color=colors.get(cid, '#cccccc'),
                opacity=0.7,
                line=dict(width=2, color='white'),
            ),
            text=[f'C{cid}'],
            textposition='middle center',
            textfont=dict(size=12, color='white'),
            name=f'Cluster {cid} ({len(points)})',
            hovertemplate=hover_text,
            customdata=[cluster_dois],  # Store DOIs for click handling
        ))

    fig.update_layout(
        xaxis=dict(showticklabels=False, showgrid=False, zeroline=False, title=''),
        yaxis=dict(showticklabels=False, showgrid=False, zeroline=False, title=''),
        hovermode='closest',
        template='plotly_white',
        clickmode='event+select',
        margin=dict(l=10, r=10, t=10, b=10),
        showlegend=True,
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
    )

    return fig


def create_network_component(elements=None, stylesheet=None,
                              embedding_data=None, clusters=None,
                              colors=None, papers=None) -> html.Div:
    """Create Cluster Bubble Chart component.

    Accepts both old-style (elements) and new-style (embedding_data, clusters, colors, papers) args
    for backward compatibility.
    """
    if embedding_data and clusters and colors and papers:
        fig = create_bubble_figure(embedding_data, clusters, colors, papers)
    else:
        # Fallback: empty figure
        fig = go.Figure()
        fig.update_layout(
            xaxis=dict(showticklabels=False, title=''),
            yaxis=dict(showticklabels=False, title=''),
            template='plotly_white',
            margin=dict(l=10, r=10, t=30, b=10),
            annotations=[dict(text='Loading cluster visualization...',
                            showarrow=False, xref='paper', yref='paper', x=0.5, y=0.5)]
        )

    return html.Div([
        dcc.Graph(
            id='cluster-bubble-chart',
            figure=fig,
            config={'displayModeBar': True, 'scrollZoom': True},
            style={'height': '600px', 'width': '100%'},
        ),
        html.Div(id='network-info', style={'marginTop': '10px'})
    ], style={'flex': '1', 'minWidth': '400px'})


# Keep these for backward compatibility (used by selection callbacks)
def get_default_stylesheet():
    """Stub for backward compatibility."""
    return []


def get_highlight_stylesheet(base_stylesheet, selected_dois):
    """Stub for backward compatibility."""
    return base_stylesheet
