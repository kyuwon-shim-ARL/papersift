"""Sidebar control panel for filtering, navigation, and re-clustering."""

from dash import html, dcc


def create_sidebar() -> html.Div:
    """
    Create sidebar with controls for filtering, navigation, and re-clustering.

    Contains:
    - Resolution slider
    - Selection actions (Keep/Exclude/Reset)
    - Navigation (Drill-down/Back)
    - Undo
    - Export
    - Statistics
    """
    return html.Div([
        html.H3('Controls', style={'marginBottom': '20px'}),

        # Resolution slider
        html.Div([
            html.Label('Cluster Resolution'),
            dcc.Slider(
                id='resolution-slider',
                min=0.1,
                max=3.0,
                step=0.1,
                value=1.0,
                marks={0.5: '0.5', 1.0: '1.0', 2.0: '2.0', 3.0: '3.0'},
                tooltip={'placement': 'bottom', 'always_visible': True},
                updatemode='mouseup',
            ),
            html.Small('Higher = more clusters', style={'color': '#666'})
        ], style={'marginBottom': '30px'}),

        # Selection actions
        html.Div([
            html.Label('Selection Actions'),
            html.Div([
                html.Button(
                    'Keep Selected',
                    id='keep-btn',
                    n_clicks=0,
                    style={
                        'width': '100%',
                        'marginBottom': '10px',
                        'backgroundColor': '#28a745',
                        'color': 'white',
                        'border': 'none',
                        'padding': '10px',
                        'cursor': 'pointer'
                    }
                ),
                html.Button(
                    'Exclude Selected',
                    id='exclude-btn',
                    n_clicks=0,
                    style={
                        'width': '100%',
                        'marginBottom': '10px',
                        'backgroundColor': '#dc3545',
                        'color': 'white',
                        'border': 'none',
                        'padding': '10px',
                        'cursor': 'pointer'
                    }
                ),
                html.Button(
                    'Reset',
                    id='reset-btn',
                    n_clicks=0,
                    style={
                        'width': '100%',
                        'marginBottom': '10px',
                        'backgroundColor': '#6c757d',
                        'color': 'white',
                        'border': 'none',
                        'padding': '10px',
                        'cursor': 'pointer'
                    }
                ),
            ])
        ], style={'marginBottom': '30px'}),

        # Navigation (drill-down)
        html.Div([
            html.Label('Navigation'),
            html.Button(
                'Drill Into Cluster',
                id='drill-btn',
                n_clicks=0,
                style={
                    'width': '100%',
                    'marginBottom': '10px',
                    'backgroundColor': '#6f42c1',
                    'color': 'white',
                    'border': 'none',
                    'padding': '10px',
                    'cursor': 'pointer'
                }
            ),
            html.Button(
                'Back (Up Level)',
                id='drill-up-btn',
                n_clicks=0,
                style={
                    'width': '100%',
                    'marginBottom': '10px',
                    'backgroundColor': '#6c757d',
                    'color': 'white',
                    'border': 'none',
                    'padding': '10px',
                    'cursor': 'pointer'
                }
            ),
        ], style={'marginBottom': '30px'}),

        # Undo
        html.Div([
            html.Label('History'),
            html.Button(
                'Undo',
                id='undo-btn',
                n_clicks=0,
                style={
                    'width': '100%',
                    'marginBottom': '10px',
                    'backgroundColor': '#fd7e14',
                    'color': 'white',
                    'border': 'none',
                    'padding': '10px',
                    'cursor': 'pointer'
                }
            ),
            html.Div(id='history-info', children='History: 0 steps',
                     style={'fontSize': '12px', 'color': '#666'})
        ], style={'marginBottom': '30px'}),

        # Export
        html.Div([
            html.Label('Export'),
            html.Button(
                'Download Filtered Papers',
                id='export-btn',
                n_clicks=0,
                style={
                    'width': '100%',
                    'backgroundColor': '#007bff',
                    'color': 'white',
                    'border': 'none',
                    'padding': '10px',
                    'cursor': 'pointer'
                }
            ),
            dcc.Download(id='download-papers'),
        ], style={'marginBottom': '30px'}),

        # Statistics
        html.Div([
            html.H4('Statistics'),
            html.Div(id='stats-display', children=[
                html.P('Total papers: -'),
                html.P('Clusters: -'),
                html.P('Selected: -'),
            ])
        ])

    ], style={
        'width': '250px',
        'padding': '20px',
        'backgroundColor': '#f8f9fa',
        'borderRight': '1px solid #dee2e6',
        'height': '100vh',
        'overflowY': 'auto'
    })
