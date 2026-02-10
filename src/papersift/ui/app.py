#!/usr/bin/env python3
"""PaperSift interactive UI main application."""

import sys
from pathlib import Path
from dash import Dash, html, dcc

from papersift.ui.components.network import create_network_component
from papersift.ui.components.table import create_table_component
from papersift.ui.components.sidebar import create_sidebar
from papersift.ui.components.landscape import create_landscape_component
from papersift.ui.utils.data_loader import (
    load_papers,
    cluster_papers,
    papers_to_cytoscape_elements,
    papers_to_table_data,
    generate_cluster_colors,
    slim_papers,
    compute_paper_embedding,
)


def create_app(papers_path: str, use_topics: bool = False) -> Dash:
    """
    Create and configure the Dash application.

    Args:
        papers_path: Path to papers JSON file
        use_topics: If True, use OpenAlex topics for enhanced clustering

    Returns:
        Configured Dash application
    """
    # Load and process data
    papers = load_papers(papers_path)

    # Detect topics presence and override use_topics if data has topics
    has_topics = any('topics' in p and p['topics'] for p in papers)
    if has_topics and not use_topics:
        use_topics = has_topics

    clusters, builder = cluster_papers(papers, resolution=1.0, use_topics=use_topics)
    elements = papers_to_cytoscape_elements(papers, clusters, builder)
    rows = papers_to_table_data(papers, clusters)
    colors = generate_cluster_colors(set(clusters.values()))

    # Compute embedding for landscape (standalone, no builder needed)
    embedding = compute_paper_embedding(papers, method="tsne", use_topics=use_topics)

    # Create app
    app = Dash(
        __name__,
        suppress_callback_exceptions=True,
        title='PaperSift - Paper Filtering UI'
    )

    # Slim papers for Store (reduces payload from 5MB to ~100KB)
    papers_slim = slim_papers(papers, keep_topics=use_topics)

    # Layout
    app.layout = html.Div([
        # Data stores
        dcc.Store(id='original-papers', data=papers_slim),
        dcc.Store(id='papers-data', data=papers_slim),
        dcc.Store(id='cluster-data', data=clusters),
        dcc.Store(id='cluster-colors', data=colors),
        dcc.Store(id='selection-store', data={'selected_dois': [], 'source': None}),
        dcc.Store(id='embedding-data', data=embedding),
        dcc.Store(id='use-topics-flag', data=use_topics),
        # Navigation state for drill-down
        dcc.Store(id='navigation-state', data={
            'path': [],
            'cluster_id': None,
        }),
        # History stack for undo
        dcc.Store(id='history-stack', storage_type='memory', data={
            'checkpoints': [],
            'current_index': -1,
            'max_size': 20,
        }),

        # Main container
        html.Div([
            # Sidebar
            create_sidebar(),

            # Main content
            html.Div([
                html.H1('PaperSift', style={'marginBottom': '20px'}),
                html.P(f'Loaded {len(papers)} papers', style={'marginBottom': '20px'}),

                # Breadcrumb placeholder
                html.Div(id='breadcrumb-container', children=[]),

                # Tabs for visualization (Network / Landscape)
                dcc.Tabs(id='view-tabs', value='network-tab', children=[
                    dcc.Tab(label='Network', value='network-tab', children=[
                        dcc.Loading(
                            id='loading-network',
                            type='default',
                            children=create_network_component(elements),
                        ),
                    ]),
                    dcc.Tab(label='Landscape', value='landscape-tab', children=[
                        dcc.Loading(
                            id='loading-landscape',
                            type='default',
                            children=create_landscape_component(
                                embedding, clusters, colors, papers_slim
                            ),
                        ),
                    ]),
                ]),

                # Table below tabs (shared by both views)
                dcc.Loading(
                    id='loading-table',
                    type='default',
                    children=create_table_component(rows),
                ),
            ], style={
                'flex': '1',
                'padding': '20px',
                'overflowY': 'auto',
                'display': 'flex',
                'flexDirection': 'column',
                'gap': '20px',
            })
        ], style={
            'display': 'flex',
            'height': '100vh'
        })
    ])

    # Register callbacks
    from papersift.ui.callbacks.selection import register_selection_callbacks
    from papersift.ui.callbacks.clustering import register_clustering_callbacks
    from papersift.ui.callbacks.navigation import register_navigation_callbacks
    from papersift.ui.callbacks.history import register_history_callbacks

    register_selection_callbacks(app)
    register_clustering_callbacks(app)
    register_navigation_callbacks(app)
    register_history_callbacks(app)

    return app


def run_server(
    papers_path: str,
    port: int = 8050,
    debug: bool = False,
    host: str = "127.0.0.1",
    use_topics: bool = False,
):
    """
    Run the Dash server.

    Args:
        papers_path: Path to papers JSON file
        port: Server port (default 8050)
        debug: Enable debug mode
        host: Server host (default 127.0.0.1, use 0.0.0.0 for external access)
        use_topics: If True, use OpenAlex topics for enhanced clustering
    """
    app = create_app(papers_path, use_topics=use_topics)
    url = f"http://{host}:{port}" if host != "0.0.0.0" else f"http://0.0.0.0:{port} (accessible externally)"
    print(f"Starting PaperSift UI at {url}")
    app.run(debug=debug, port=port, host=host)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python app.py <papers.json>")
        sys.exit(1)

    run_server(sys.argv[1], debug=True)
