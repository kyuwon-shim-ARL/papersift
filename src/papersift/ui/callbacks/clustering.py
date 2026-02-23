"""Callbacks for re-clustering and filtering operations."""

import json
from dash import callback, Input, Output, State, ctx, no_update, dcc


def _push_checkpoint(history, checkpoint):
    """Push a checkpoint onto the history stack."""
    h = dict(history)
    checkpoints = list(h.get('checkpoints', []))
    max_size = h.get('max_size', 20)

    checkpoints.append(checkpoint)
    if len(checkpoints) > max_size:
        checkpoints = checkpoints[-max_size:]

    h['checkpoints'] = checkpoints
    h['current_index'] = len(checkpoints) - 1
    return h


def register_clustering_callbacks(app):
    """Register all clustering-related callbacks."""

    # Resolution change -> Re-cluster (only Leiden, not embedding)
    @app.callback(
        Output('cluster-data', 'data'),
        Output('cluster-bubble-chart', 'figure'),
        Output('paper-table', 'rowData'),
        Output('cluster-colors', 'data'),
        Output('embedding-data', 'data'),
        Input('resolution-slider', 'value'),
        State('papers-data', 'data'),
        State('original-papers', 'data'),
        State('use-topics-flag', 'data'),
        State('embedding-data', 'data'),
        prevent_initial_call=True
    )
    def recluster_on_resolution(resolution, papers, original_papers, use_topics, existing_embedding):
        from papersift.ui.utils.data_loader import (
            cluster_papers,
            papers_to_table_data,
            generate_cluster_colors,
        )
        from papersift.ui.components.network import create_bubble_figure

        if not papers:
            return no_update, no_update, no_update, no_update, no_update

        # Only re-run Leiden clustering (resolution doesn't affect embedding)
        clusters, builder = cluster_papers(papers, resolution=resolution, use_topics=bool(use_topics))
        rows = papers_to_table_data(papers, clusters)
        colors = generate_cluster_colors(set(clusters.values()))

        # Use existing embedding for bubble figure (don't recompute!)
        bubble_fig = create_bubble_figure(existing_embedding, clusters, colors, papers)

        # Return no_update for embedding-data (hasn't changed)
        return clusters, bubble_fig, rows, colors, no_update

    # Keep Selected button
    @app.callback(
        Output('papers-data', 'data', allow_duplicate=True),
        Output('cluster-data', 'data', allow_duplicate=True),
        Output('cluster-bubble-chart', 'figure', allow_duplicate=True),
        Output('paper-table', 'rowData', allow_duplicate=True),
        Output('cluster-colors', 'data', allow_duplicate=True),
        Output('selection-store', 'data', allow_duplicate=True),
        Output('embedding-data', 'data', allow_duplicate=True),
        Output('history-stack', 'data', allow_duplicate=True),
        Input('keep-btn', 'n_clicks'),
        State('selection-store', 'data'),
        State('papers-data', 'data'),
        State('cluster-data', 'data'),
        State('resolution-slider', 'value'),
        State('use-topics-flag', 'data'),
        State('navigation-state', 'data'),
        State('history-stack', 'data'),
        prevent_initial_call=True
    )
    def keep_selected(n_clicks, selection, papers, current_clusters, resolution,
                      use_topics, nav_state, history):
        from papersift.ui.utils.data_loader import (
            cluster_papers,
            papers_to_table_data,
            generate_cluster_colors,
            compute_paper_embedding,
        )
        from papersift.ui.components.network import create_bubble_figure

        if not selection or not selection.get('selected_dois'):
            return (no_update,) * 8

        selected_dois = set(selection['selected_dois'])
        filtered_papers = [p for p in papers if p['doi'] in selected_dois]

        if not filtered_papers or len(filtered_papers) < 2:
            return (no_update,) * 8

        # Save checkpoint before action
        checkpoint = {
            'dois': [p['doi'] for p in papers],
            'clusters': dict(current_clusters) if current_clusters else {},
            'navigation_path': list(nav_state.get('path', [])),
            'resolution': resolution,
            'action': 'keep',
            'description': f'Kept {len(filtered_papers)} papers',
        }
        history = _push_checkpoint(history, checkpoint)

        clusters, builder = cluster_papers(filtered_papers, resolution=resolution, use_topics=bool(use_topics))
        rows = papers_to_table_data(filtered_papers, clusters)
        colors = generate_cluster_colors(set(clusters.values()))
        # Paper set changed - recompute embedding (uses cache)
        embedding = compute_paper_embedding(filtered_papers, method="tsne", use_topics=bool(use_topics))
        bubble_fig = create_bubble_figure(embedding, clusters, colors, filtered_papers)

        return (filtered_papers, clusters, bubble_fig, rows, colors,
                {'selected_dois': [], 'source': 'reset'}, embedding, history)

    # Exclude Selected button
    @app.callback(
        Output('papers-data', 'data', allow_duplicate=True),
        Output('cluster-data', 'data', allow_duplicate=True),
        Output('cluster-bubble-chart', 'figure', allow_duplicate=True),
        Output('paper-table', 'rowData', allow_duplicate=True),
        Output('cluster-colors', 'data', allow_duplicate=True),
        Output('selection-store', 'data', allow_duplicate=True),
        Output('embedding-data', 'data', allow_duplicate=True),
        Output('history-stack', 'data', allow_duplicate=True),
        Input('exclude-btn', 'n_clicks'),
        State('selection-store', 'data'),
        State('papers-data', 'data'),
        State('cluster-data', 'data'),
        State('resolution-slider', 'value'),
        State('use-topics-flag', 'data'),
        State('navigation-state', 'data'),
        State('history-stack', 'data'),
        prevent_initial_call=True
    )
    def exclude_selected(n_clicks, selection, papers, current_clusters, resolution,
                         use_topics, nav_state, history):
        from papersift.ui.utils.data_loader import (
            cluster_papers,
            papers_to_table_data,
            generate_cluster_colors,
            compute_paper_embedding,
        )
        from papersift.ui.components.network import create_bubble_figure

        if not selection or not selection.get('selected_dois'):
            return (no_update,) * 8

        selected_dois = set(selection['selected_dois'])
        filtered_papers = [p for p in papers if p['doi'] not in selected_dois]

        if not filtered_papers or len(filtered_papers) < 2:
            return (no_update,) * 8

        # Save checkpoint before action
        checkpoint = {
            'dois': [p['doi'] for p in papers],
            'clusters': dict(current_clusters) if current_clusters else {},
            'navigation_path': list(nav_state.get('path', [])),
            'resolution': resolution,
            'action': 'exclude',
            'description': f'Excluded {len(selected_dois)} papers',
        }
        history = _push_checkpoint(history, checkpoint)

        clusters, builder = cluster_papers(filtered_papers, resolution=resolution, use_topics=bool(use_topics))
        rows = papers_to_table_data(filtered_papers, clusters)
        colors = generate_cluster_colors(set(clusters.values()))
        # Paper set changed - recompute embedding (uses cache)
        embedding = compute_paper_embedding(filtered_papers, method="tsne", use_topics=bool(use_topics))
        bubble_fig = create_bubble_figure(embedding, clusters, colors, filtered_papers)

        return (filtered_papers, clusters, bubble_fig, rows, colors,
                {'selected_dois': [], 'source': 'reset'}, embedding, history)

    # Reset button
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
        Input('reset-btn', 'n_clicks'),
        State('original-papers', 'data'),
        State('resolution-slider', 'value'),
        State('use-topics-flag', 'data'),
        prevent_initial_call=True
    )
    def reset_papers(n_clicks, original_papers, resolution, use_topics):
        from papersift.ui.utils.data_loader import (
            cluster_papers,
            papers_to_table_data,
            generate_cluster_colors,
            compute_paper_embedding,
        )
        from papersift.ui.components.network import create_bubble_figure

        if not original_papers:
            return (no_update,) * 9

        clusters, builder = cluster_papers(original_papers, resolution=resolution, use_topics=bool(use_topics))
        rows = papers_to_table_data(original_papers, clusters)
        colors = generate_cluster_colors(set(clusters.values()))
        # Paper set changed (back to original) - recompute embedding (uses cache)
        embedding = compute_paper_embedding(original_papers, method="tsne", use_topics=bool(use_topics))
        bubble_fig = create_bubble_figure(embedding, clusters, colors, original_papers)

        nav_state = {'path': [], 'cluster_id': None}
        history = {'checkpoints': [], 'current_index': -1, 'max_size': 20}

        return (original_papers, clusters, bubble_fig, rows, colors,
                {'selected_dois': [], 'source': 'reset'}, embedding, nav_state, history)

    # Export button
    @app.callback(
        Output('download-papers', 'data'),
        Input('export-btn', 'n_clicks'),
        State('papers-data', 'data'),
        State('cluster-data', 'data'),
        prevent_initial_call=True
    )
    def export_papers(n_clicks, papers, clusters):
        if not papers:
            return no_update

        # Add cluster assignments to papers
        export_data = []
        for paper in papers:
            p = paper.copy()
            p['cluster'] = clusters.get(paper['doi'], -1)
            export_data.append(p)

        return dcc.send_string(
            json.dumps({'papers': export_data}, indent=2),
            'filtered_papers.json'
        )
