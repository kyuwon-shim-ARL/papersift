"""Chat panel component with dual-purpose: chat mode and detail view."""

from dash import html, dcc


def create_chat_panel() -> html.Div:
    """Create a dual-purpose right panel with chat and paper detail views.

    Chat mode (default): message history, input box, submit button.
    Detail mode: paper metadata shown on paper click, with Back to Chat button.
    """
    return html.Div(
        id='chat-panel',
        children=[
            # Stores
            dcc.Store(id='chat-history', storage_type='memory', data={'messages': []}),

            # Header
            html.Div([
                html.Span(
                    'Research Assistant',
                    style={
                        'fontWeight': '600',
                        'fontSize': '16px',
                        'color': 'var(--text-primary)',
                    },
                ),
                html.Button(
                    '\u00d7',
                    id='chat-close-btn',
                    n_clicks=0,
                    style={
                        'background': 'none',
                        'border': 'none',
                        'fontSize': '20px',
                        'cursor': 'pointer',
                        'color': 'var(--text-secondary)',
                        'padding': '0 4px',
                        'lineHeight': '1',
                    },
                ),
            ], style={
                'display': 'flex',
                'justifyContent': 'space-between',
                'alignItems': 'center',
                'padding': '12px 15px',
                'borderBottom': '1px solid var(--border-color)',
                'flexShrink': '0',
            }),

            # Chat view (default)
            html.Div(
                id='chat-view',
                children=[
                    # Message history (scrollable)
                    html.Div(
                        id='chat-messages',
                        children=[
                            html.P(
                                'Ask questions about the paper landscape. '
                                'I can help you explore clusters, find patterns, '
                                'and navigate the dataset.',
                                style={
                                    'color': 'var(--text-secondary)',
                                    'fontSize': '13px',
                                    'fontStyle': 'italic',
                                    'padding': '10px',
                                },
                            ),
                        ],
                        style={
                            'flex': '1',
                            'overflowY': 'auto',
                            'padding': '10px',
                            'display': 'flex',
                            'flexDirection': 'column',
                            'gap': '8px',
                        },
                    ),

                    # Loading indicator
                    html.Div(
                        id='chat-loading',
                        children=[
                            html.Div(
                                'Thinking...',
                                style={
                                    'color': 'var(--accent)',
                                    'fontSize': '13px',
                                    'padding': '6px 12px',
                                    'fontStyle': 'italic',
                                },
                            ),
                        ],
                        style={'display': 'none', 'flexShrink': '0'},
                    ),

                    # Input area
                    html.Div([
                        dcc.Textarea(
                            id='chat-input',
                            placeholder='Ask about the paper landscape...',
                            style={
                                'width': '100%',
                                'resize': 'none',
                                'borderRadius': '6px',
                                'border': '1px solid var(--border-color)',
                                'padding': '8px 10px',
                                'fontSize': '13px',
                                'backgroundColor': 'var(--bg-card)',
                                'color': 'var(--text-primary)',
                                'fontFamily': 'inherit',
                                'boxSizing': 'border-box',
                            },
                            rows=2,
                        ),
                        html.Button(
                            'Send',
                            id='chat-submit-btn',
                            n_clicks=0,
                            style={
                                'width': '100%',
                                'marginTop': '6px',
                                'padding': '8px',
                                'backgroundColor': 'var(--accent)',
                                'color': '#ffffff',
                                'border': 'none',
                                'borderRadius': '6px',
                                'cursor': 'pointer',
                                'fontSize': '13px',
                                'fontWeight': '500',
                            },
                        ),
                    ], style={
                        'padding': '10px',
                        'borderTop': '1px solid var(--border-color)',
                        'flexShrink': '0',
                    }),

                    # Context info
                    html.Div(
                        id='chat-context-info',
                        children='Context: loading...',
                        style={
                            'padding': '6px 15px 10px',
                            'fontSize': '11px',
                            'color': 'var(--text-secondary)',
                            'borderTop': '1px solid var(--border-color)',
                            'flexShrink': '0',
                        },
                    ),
                ],
                style={
                    'display': 'flex',
                    'flexDirection': 'column',
                    'flex': '1',
                    'overflow': 'hidden',
                },
            ),

            # Detail view (hidden by default)
            html.Div(
                id='detail-view',
                children=[
                    html.Button(
                        '\u2190 Back to Chat',
                        id='chat-back-btn',
                        n_clicks=0,
                        style={
                            'background': 'none',
                            'border': '1px solid var(--border-color)',
                            'borderRadius': '4px',
                            'padding': '4px 10px',
                            'cursor': 'pointer',
                            'fontSize': '12px',
                            'color': 'var(--accent)',
                            'marginBottom': '10px',
                        },
                    ),
                    html.H3(id='detail-title', children='Select a paper to view details',
                             style={'fontSize': '15px', 'marginBottom': '10px'}),
                    html.Hr(style={'borderColor': 'var(--border-color)', 'margin': '8px 0'}),
                    html.Div(id='detail-meta', children=[]),
                    html.Div(id='detail-abstract', children=[]),
                    html.Hr(style={'borderColor': 'var(--border-color)', 'margin': '8px 0'}),
                    html.Div(id='detail-cluster-info', children=[]),
                ],
                style={
                    'display': 'none',
                    'padding': '15px',
                    'overflowY': 'auto',
                    'flex': '1',
                },
            ),
        ],
        style={
            'width': '380px',
            'display': 'none',
            'flexDirection': 'column',
            'flexShrink': '0',
            'backgroundColor': 'var(--bg-card)',
            'borderLeft': '1px solid var(--border-color)',
            'height': '100vh',
        },
    )
