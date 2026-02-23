"""Callbacks for undo/history system with lightweight checkpoints."""

from dash import Input, Output, State, no_update


def register_history_callbacks(app):
    """Register undo and history display callbacks."""

    # Undo button
    @app.callback(
        Output('papers-data', 'data', allow_duplicate=True),
        Output('cluster-data', 'data', allow_duplicate=True),
        Output('cluster-bubble-chart', 'figure', allow_duplicate=True),
        Output('paper-table', 'rowData', allow_duplicate=True),
        Output('cluster-colors', 'data', allow_duplicate=True),
        Output('selection-store', 'data', allow_duplicate=True),
        Output('embedding-data', 'data', allow_duplicate=True),
        Output('navigation-state', 'data', allow_duplicate=True),
        Output('history-stack', 'data', allow_duplicate=True),
        Output('breadcrumb-container', 'children', allow_duplicate=True),
        Input('undo-btn', 'n_clicks'),
        State('history-stack', 'data'),
        State('original-papers', 'data'),
        State('resolution-slider', 'value'),
        State('use-topics-flag', 'data'),
        prevent_initial_call=True
    )
    def undo_action(n_clicks, history, original_papers, resolution, use_topics):
        from papersift.ui.utils.data_loader import (
            cluster_papers,
            papers_to_table_data,
            generate_cluster_colors,
            compute_paper_embedding,
        )
        from papersift.ui.components.network import create_bubble_figure
        from papersift.ui.components.breadcrumb import create_breadcrumb

        checkpoints = history.get('checkpoints', [])
        if not checkpoints:
            return (no_update,) * 10

        # Pop the last checkpoint to restore
        cp = checkpoints[-1]
        restored_dois = set(cp['dois'])
        restored_papers = [p for p in original_papers if p['doi'] in restored_dois]
        restored_clusters = cp['clusters']
        restored_path = cp.get('navigation_path', [])

        if not restored_papers or len(restored_papers) < 2:
            return (no_update,) * 10

        # Rebuild visualization from checkpoint
        _, builder = cluster_papers(
            restored_papers, resolution=cp.get('resolution', resolution),
            use_topics=bool(use_topics)
        )
        rows = papers_to_table_data(restored_papers, restored_clusters)
        colors = generate_cluster_colors(set(restored_clusters.values()))
        embedding = compute_paper_embedding(restored_papers, method="tsne", use_topics=bool(use_topics))
        bubble_fig = create_bubble_figure(embedding, restored_clusters, colors, restored_papers)

        # Update history (pop the checkpoint)
        new_history = dict(history)
        new_history['checkpoints'] = checkpoints[:-1]
        new_history['current_index'] = len(checkpoints) - 2

        nav_state = {'path': restored_path, 'cluster_id': restored_path[-1] if restored_path else None}
        breadcrumb = create_breadcrumb(restored_path)

        return (restored_papers, restored_clusters, bubble_fig, rows, colors,
                {'selected_dois': [], 'source': 'reset'}, embedding,
                nav_state, new_history, breadcrumb)

    # History info display
    @app.callback(
        Output('history-info', 'children'),
        Input('history-stack', 'data'),
    )
    def update_history_info(history):
        n = len(history.get('checkpoints', [])) if history else 0
        return f'History: {n} step{"s" if n != 1 else ""}'
