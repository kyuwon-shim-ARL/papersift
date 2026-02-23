"""Sidebar control panel for filtering, navigation, and re-clustering."""

from dash import html, dcc
from papersift.ui.components.theme import create_theme_toggle


def create_sidebar() -> html.Div:
    """
    Create sidebar with controls for filtering, navigation, and re-clustering.

    Contains:
    - Theme toggle
    - Resolution slider
    - Selection actions (Keep/Exclude/Reset)
    - Navigation (Drill-down/Back)
    - Undo
    - Export
    - Statistics
    """
    return html.Div([
        # Theme toggle at top
        create_theme_toggle(),
        html.Hr(style={'borderColor': 'var(--border-color)', 'margin': '20px 0'}),

        html.H3('Controls', style={'marginBottom': '20px'}),

        # 1. Clustering (open by default)
        html.Details([
            html.Summary('Clustering', style={
                'cursor': 'pointer',
                'fontWeight': '600',
                'marginBottom': '10px',
                'fontSize': '15px',
                'color': 'var(--text-primary)',
                'padding': '8px 0'
            }),
            html.Div([
                html.Label('Cluster Granularity'),
                html.Small('fewer ← slider → more clusters', style={
                    'display': 'block',
                    'color': 'var(--text-secondary)',
                    'fontSize': '11px',
                    'marginBottom': '8px'
                }),
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
            ], style={'paddingLeft': '10px'})
        ], open=True, style={'marginBottom': '20px'}),

        # 2. Selection (open by default)
        html.Details([
            html.Summary('Selection', style={
                'cursor': 'pointer',
                'fontWeight': '600',
                'marginBottom': '10px',
                'fontSize': '15px',
                'color': 'var(--text-primary)',
                'padding': '8px 0'
            }),
            html.Div([
                html.Button(
                    'Keep Selected',
                    id='keep-btn',
                    n_clicks=0,
                    title='Keep only the selected papers and re-cluster',
                    style={
                        'width': '100%',
                        'marginBottom': '10px',
                        'backgroundColor': '#28a745',
                        'color': 'white',
                        'border': 'none',
                        'padding': '10px',
                        'cursor': 'pointer',
                        'borderRadius': '4px'
                    }
                ),
                html.Button(
                    'Remove Selected',
                    id='exclude-btn',
                    n_clicks=0,
                    title='Remove selected papers and re-cluster',
                    style={
                        'width': '100%',
                        'marginBottom': '10px',
                        'backgroundColor': '#dc3545',
                        'color': 'white',
                        'border': 'none',
                        'padding': '10px',
                        'cursor': 'pointer',
                        'borderRadius': '4px'
                    }
                ),
                html.Button(
                    'Reset All',
                    id='reset-btn',
                    n_clicks=0,
                    title='Restore all original papers',
                    style={
                        'width': '100%',
                        'marginBottom': '10px',
                        'backgroundColor': '#6c757d',
                        'color': 'white',
                        'border': 'none',
                        'padding': '10px',
                        'cursor': 'pointer',
                        'borderRadius': '4px'
                    }
                ),
            ], style={'paddingLeft': '10px'})
        ], open=True, style={'marginBottom': '20px'}),

        # 3. Navigation (collapsed)
        html.Details([
            html.Summary('Navigation', style={
                'cursor': 'pointer',
                'fontWeight': '600',
                'marginBottom': '10px',
                'fontSize': '15px',
                'color': 'var(--text-primary)',
                'padding': '8px 0'
            }),
            html.Div([
                html.Button(
                    'Drill Into Cluster',
                    id='drill-btn',
                    n_clicks=0,
                    title='Create sub-clusters within the selected cluster',
                    style={
                        'width': '100%',
                        'marginBottom': '10px',
                        'backgroundColor': '#6f42c1',
                        'color': 'white',
                        'border': 'none',
                        'padding': '10px',
                        'cursor': 'pointer',
                        'borderRadius': '4px'
                    }
                ),
                html.Button(
                    'Back (Up Level)',
                    id='drill-up-btn',
                    n_clicks=0,
                    title='Return to previous clustering level',
                    style={
                        'width': '100%',
                        'marginBottom': '10px',
                        'backgroundColor': '#6c757d',
                        'color': 'white',
                        'border': 'none',
                        'padding': '10px',
                        'cursor': 'pointer',
                        'borderRadius': '4px'
                    }
                ),
            ], style={'paddingLeft': '10px'})
        ], open=False, style={'marginBottom': '20px'}),

        # 4. History (collapsed)
        html.Details([
            html.Summary('History', style={
                'cursor': 'pointer',
                'fontWeight': '600',
                'marginBottom': '10px',
                'fontSize': '15px',
                'color': 'var(--text-primary)',
                'padding': '8px 0'
            }),
            html.Div([
                html.Button(
                    'Undo',
                    id='undo-btn',
                    n_clicks=0,
                    title='Undo the last action',
                    style={
                        'width': '100%',
                        'marginBottom': '10px',
                        'backgroundColor': '#fd7e14',
                        'color': 'white',
                        'border': 'none',
                        'padding': '10px',
                        'cursor': 'pointer',
                        'borderRadius': '4px'
                    }
                ),
                html.Div(id='history-info', children='History: 0 steps',
                         style={'fontSize': '12px', 'color': 'var(--text-secondary)'})
            ], style={'paddingLeft': '10px'})
        ], open=False, style={'marginBottom': '20px'}),

        # 5. Export (collapsed)
        html.Details([
            html.Summary('Export', style={
                'cursor': 'pointer',
                'fontWeight': '600',
                'marginBottom': '10px',
                'fontSize': '15px',
                'color': 'var(--text-primary)',
                'padding': '8px 0'
            }),
            html.Div([
                html.Button(
                    'Download Filtered Papers',
                    id='export-btn',
                    n_clicks=0,
                    title='Export current papers as JSON',
                    style={
                        'width': '100%',
                        'backgroundColor': '#007bff',
                        'color': 'white',
                        'border': 'none',
                        'padding': '10px',
                        'cursor': 'pointer',
                        'borderRadius': '4px'
                    }
                ),
                dcc.Download(id='download-papers'),
            ], style={'paddingLeft': '10px'})
        ], open=False, style={'marginBottom': '20px'}),

        # Chat toggle
        html.Div([
            html.Button(
                'Open Chat',
                id='chat-toggle-btn',
                n_clicks=0,
                title='Open research assistant chat panel',
                style={
                    'width': '100%',
                    'padding': '10px',
                    'backgroundColor': 'var(--accent)',
                    'color': '#ffffff',
                    'border': 'none',
                    'borderRadius': '4px',
                    'cursor': 'pointer',
                    'fontWeight': '500',
                },
            ),
        ], style={'marginBottom': '20px'}),

        # Statistics
        html.Div([
            html.H4('Statistics'),
            html.Div(id='stats-display', children=[
                html.P('Total papers: -'),
                html.P('Clusters: -'),
                html.P('Selected: -'),
            ])
        ])

    ], className='sidebar-container', style={
        'width': '250px',
        'padding': '20px',
        'height': '100vh',
        'overflowY': 'auto'
    })
