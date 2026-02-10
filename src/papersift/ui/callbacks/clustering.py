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

    # Resolution change -> Re-cluster
    @app.callback(
        Output('cluster-data', 'data'),
        Output('cytoscape-network', 'elements'),
        Output('paper-table', 'rowData'),
        Output('cluster-colors', 'data'),
        Output('embedding-data', 'data'),
        Input('resolution-slider', 'value'),
        State('papers-data', 'data'),
        State('original-papers', 'data'),
        State('use-topics-flag', 'data'),
        prevent_initial_call=True
    )
    def recluster_on_resolution(resolution, papers, original_papers, use_topics):
        from papersift.ui.utils.data_loader import (
            cluster_papers,
            papers_to_cytoscape_elements,
            papers_to_table_data,
            generate_cluster_colors,
            compute_paper_embedding,
        )

        if not papers:
            return no_update, no_update, no_update, no_update, no_update

        clusters, builder = cluster_papers(papers, resolution=resolution, use_topics=bool(use_topics))
        elements = papers_to_cytoscape_elements(papers, clusters, builder)
        rows = papers_to_table_data(papers, clusters)
        colors = generate_cluster_colors(set(clusters.values()))
        embedding = compute_paper_embedding(papers, method="tsne", use_topics=bool(use_topics))

        return clusters, elements, rows, colors, embedding

    # Keep Selected button
    @app.callback(
        Output('papers-data', 'data', allow_duplicate=True),
        Output('cluster-data', 'data', allow_duplicate=True),
        Output('cytoscape-network', 'elements', allow_duplicate=True),
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
            papers_to_cytoscape_elements,
            papers_to_table_data,
            generate_cluster_colors,
            compute_paper_embedding,
        )

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
        elements = papers_to_cytoscape_elements(filtered_papers, clusters, builder)
        rows = papers_to_table_data(filtered_papers, clusters)
        colors = generate_cluster_colors(set(clusters.values()))
        embedding = compute_paper_embedding(filtered_papers, method="tsne", use_topics=bool(use_topics))

        return (filtered_papers, clusters, elements, rows, colors,
                {'selected_dois': [], 'source': 'reset'}, embedding, history)

    # Exclude Selected button
    @app.callback(
        Output('papers-data', 'data', allow_duplicate=True),
        Output('cluster-data', 'data', allow_duplicate=True),
        Output('cytoscape-network', 'elements', allow_duplicate=True),
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
            papers_to_cytoscape_elements,
            papers_to_table_data,
            generate_cluster_colors,
            compute_paper_embedding,
        )

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
        elements = papers_to_cytoscape_elements(filtered_papers, clusters, builder)
        rows = papers_to_table_data(filtered_papers, clusters)
        colors = generate_cluster_colors(set(clusters.values()))
        embedding = compute_paper_embedding(filtered_papers, method="tsne", use_topics=bool(use_topics))

        return (filtered_papers, clusters, elements, rows, colors,
                {'selected_dois': [], 'source': 'reset'}, embedding, history)

    # Reset button
    @app.callback(
        Output('papers-data', 'data', allow_duplicate=True),
        Output('cluster-data', 'data', allow_duplicate=True),
        Output('cytoscape-network', 'elements', allow_duplicate=True),
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
            papers_to_cytoscape_elements,
            papers_to_table_data,
            generate_cluster_colors,
            compute_paper_embedding,
        )

        if not original_papers:
            return (no_update,) * 9

        clusters, builder = cluster_papers(original_papers, resolution=resolution, use_topics=bool(use_topics))
        elements = papers_to_cytoscape_elements(original_papers, clusters, builder)
        rows = papers_to_table_data(original_papers, clusters)
        colors = generate_cluster_colors(set(clusters.values()))
        embedding = compute_paper_embedding(original_papers, method="tsne", use_topics=bool(use_topics))

        nav_state = {'path': [], 'cluster_id': None}
        history = {'checkpoints': [], 'current_index': -1, 'max_size': 20}

        return (original_papers, clusters, elements, rows, colors,
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
