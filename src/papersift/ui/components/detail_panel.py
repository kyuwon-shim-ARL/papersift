"""Paper detail panel component for showing individual paper metadata."""

from dash import html, dcc


def create_detail_panel() -> html.Div:
    """Create an initially-hidden detail panel that shows paper info on selection."""
    return html.Div(
        id='detail-panel',
        children=[
            html.Div([
                html.H3(id='detail-title', children='Select a paper to view details'),
                html.Button('×', id='detail-close-btn', n_clicks=0,
                           style={'position': 'absolute', 'top': '10px', 'right': '15px',
                                  'background': 'none', 'border': 'none', 'fontSize': '20px',
                                  'cursor': 'pointer', 'color': 'var(--text-secondary)'}),
            ], style={'position': 'relative'}),
            html.Hr(),
            html.Div(id='detail-meta', children=[]),  # Year, DOI link
            html.Div(id='detail-abstract', children=[]),  # Abstract text
            html.Hr(),
            html.Div(id='detail-cluster-info', children=[]),  # Cluster, entities
        ],
        style={
            'width': '350px',
            'padding': '15px',
            'overflowY': 'auto',
            'display': 'none',  # Hidden by default
            'flexShrink': '0',
        }
    )
