"""Breadcrumb navigation component for drill-down hierarchy."""

from dash import html


def create_breadcrumb(path: list) -> html.Div:
    """
    Render breadcrumb navigation showing the drill-down hierarchy.

    Args:
        path: list of cluster IDs forming the drill-down path
              [] -> "All Papers"
              [3] -> "All Papers > Cluster 3"
              [3, 1] -> "All Papers > Cluster 3 > Sub 3.1"

    Returns:
        html.Div with breadcrumb trail
    """
    items = [html.Span('All Papers', style={'fontWeight': 'bold'})]

    for i, cid in enumerate(path):
        items.append(html.Span(' > ', style={'color': '#999', 'margin': '0 4px'}))
        label = f'Cluster {cid}' if i == 0 else f'Sub {".".join(str(x) for x in path[:i+1])}'
        if i == len(path) - 1:
            # Current level (not clickable)
            items.append(html.Span(label, style={'fontWeight': 'bold', 'color': '#6f42c1'}))
        else:
            items.append(html.Span(label, style={'color': '#007bff'}))

    return html.Div(
        children=items,
        style={
            'padding': '8px 12px',
            'backgroundColor': '#f0f0f0',
            'borderRadius': '4px',
            'fontSize': '14px',
        }
    )
