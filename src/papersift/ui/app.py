#!/usr/bin/env python3
"""PaperSift interactive UI main application."""

import sys
import json
from pathlib import Path
from dash import Dash, html, dcc

try:
    import diskcache
    from dash import DiskcacheManager
    _HAS_DISKCACHE = True
except ImportError:
    _HAS_DISKCACHE = False

from papersift.ui.components.network import create_network_component
from papersift.ui.components.table import create_table_component
from papersift.ui.components.sidebar import create_sidebar
from papersift.ui.components.landscape import create_landscape_component
from papersift.ui.components.chat_panel import create_chat_panel
from papersift.ui.components.theme import get_theme_style_element
from papersift.ui.components.analysis import load_analysis_data, create_analysis_component
from papersift.ui.utils.data_loader import (
    load_papers,
    cluster_papers,
    papers_to_table_data,
    generate_cluster_colors,
    slim_papers,
    compute_paper_embedding,
)


def create_app(papers_path: str, use_topics: bool = False, analysis_dir: str = None) -> Dash:
    """
    Create and configure the Dash application.

    Args:
        papers_path: Path to papers JSON file
        use_topics: If True, use OpenAlex topics for enhanced clustering
        analysis_dir: Optional directory containing analysis JSON files
                      (method_flows.json, trend_analysis.json, hypotheses.json)

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
    rows = papers_to_table_data(papers, clusters)
    colors = generate_cluster_colors(set(clusters.values()))

    # Compute embedding for landscape (standalone, no builder needed)
    embedding = compute_paper_embedding(papers, method="tsne", use_topics=use_topics)

    # Load analysis data if directory provided
    analysis_data = load_analysis_data(analysis_dir) if analysis_dir else {}

    # Load extractions if available
    extractions = {}
    if analysis_dir:
        ext_path = Path(analysis_dir) / 'extractions_all.json'
        if ext_path.exists():
            try:
                with open(ext_path) as f:
                    ext_data = json.load(f)
                # Build doi -> extraction dict
                if isinstance(ext_data, list):
                    extractions = {e['doi']: e for e in ext_data if 'doi' in e}
                elif isinstance(ext_data, dict):
                    # Handle nested structure
                    ext_list = ext_data.get('papers', ext_data.get('extractions', []))
                    extractions = {e['doi']: e for e in ext_list if 'doi' in e}
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Could not load extractions from {ext_path}: {e}")

    # Create app with optional background callback support
    app_kwargs = dict(
        suppress_callback_exceptions=True,
        title='PaperSift - Paper Filtering UI',
    )
    if _HAS_DISKCACHE:
        try:
            cache = diskcache.Cache("/tmp/papersift-cache")
            app_kwargs['background_callback_manager'] = DiskcacheManager(cache)
        except (ImportError, Exception):
            pass  # multiprocess not installed; chat will work synchronously
    app = Dash(__name__, **app_kwargs)

    # Slim papers for Store (reduces payload from 5MB to ~100KB)
    papers_slim = slim_papers(papers, keep_topics=use_topics, keep_abstract=True)

    # Layout
    app.layout = html.Div([
        # Theme CSS
        get_theme_style_element(),

        # Data stores
        dcc.Store(id='original-papers', data=papers_slim),
        dcc.Store(id='papers-data', data=papers_slim),
        dcc.Store(id='cluster-data', data=clusters),
        dcc.Store(id='cluster-colors', data=colors),
        dcc.Store(id='selection-store', data={'selected_dois': [], 'source': None}),
        dcc.Store(id='embedding-data', data=embedding),
        dcc.Store(id='use-topics-flag', data=use_topics),
        dcc.Store(id='extractions-data', data=extractions),
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
                dcc.Tabs(id='view-tabs', value='network-tab', className='tab-container', children=[
                    dcc.Tab(label='Network', value='network-tab', children=[
                        dcc.Loading(
                            id='loading-network',
                            type='default',
                            children=create_network_component(
                                embedding_data=embedding,
                                clusters=clusters,
                                colors=colors,
                                papers=papers_slim,
                            ),
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
                ] + ([
                    dcc.Tab(label='Analysis', value='analysis-tab', children=[
                        create_analysis_component(analysis_data),
                    ]),
                ] if any(v is not None for v in analysis_data.values()) else [])),

                # Collapsible table (hidden by default so charts are visible)
                html.Div([
                    html.Button(
                        f'Show Paper Table ({len(papers)} papers)',
                        id='toggle-table-btn',
                        n_clicks=0,
                        style={
                            'width': '100%', 'padding': '10px',
                            'backgroundColor': 'var(--bg-secondary)',
                            'color': 'var(--text-primary)',
                            'border': '1px solid var(--border-color)',
                            'borderRadius': '6px', 'cursor': 'pointer',
                            'fontSize': '14px', 'fontWeight': '500',
                        }
                    ),
                    html.Div(
                        id='table-container',
                        children=dcc.Loading(
                            id='loading-table',
                            type='default',
                            children=create_table_component(rows),
                        ),
                        style={'display': 'none'},  # Hidden by default
                    ),
                ]),
            ], className='main-content', style={
                'flex': '1',
                'padding': '20px',
                'overflowY': 'auto',
                'display': 'flex',
                'flexDirection': 'column',
                'gap': '20px',
            }),

            # Chat panel with detail view (right side)
            create_chat_panel(),
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
    from papersift.ui.callbacks.chat import register_chat_callbacks
    from papersift.ui.callbacks.theme import register_theme_callbacks
    from papersift.ui.callbacks.analysis import register_analysis_callbacks

    register_selection_callbacks(app)
    register_clustering_callbacks(app)
    register_navigation_callbacks(app)
    register_history_callbacks(app)
    register_chat_callbacks(app)
    register_theme_callbacks(app)
    register_analysis_callbacks(app)

    return app


def run_server(
    papers_path: str,
    port: int = 8050,
    debug: bool = False,
    host: str = "127.0.0.1",
    use_topics: bool = False,
    analysis_dir: str = None,
):
    """
    Run the Dash server.

    Args:
        papers_path: Path to papers JSON file
        port: Server port (default 8050)
        debug: Enable debug mode
        host: Server host (default 127.0.0.1, use 0.0.0.0 for external access)
        use_topics: If True, use OpenAlex topics for enhanced clustering
        analysis_dir: Optional directory containing analysis JSON files
    """
    app = create_app(papers_path, use_topics=use_topics, analysis_dir=analysis_dir)
    url = f"http://{host}:{port}" if host != "0.0.0.0" else f"http://0.0.0.0:{port} (accessible externally)"
    print(f"Starting PaperSift UI at {url}")
    app.run(debug=debug, port=port, host=host)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python app.py <papers.json>")
        sys.exit(1)

    run_server(sys.argv[1], debug=True)
