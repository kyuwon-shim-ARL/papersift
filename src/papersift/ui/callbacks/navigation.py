"""Callbacks for drill-down navigation and breadcrumb updates."""

from dash import Input, Output, State, no_update


def register_navigation_callbacks(app):
    """Register drill-down and breadcrumb navigation callbacks."""

    # Drill Into Cluster
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
        Output('breadcrumb-container', 'children', allow_duplicate=True),
        Input('drill-btn', 'n_clicks'),
        State('selection-store', 'data'),
        State('papers-data', 'data'),
        State('cluster-data', 'data'),
        State('resolution-slider', 'value'),
        State('use-topics-flag', 'data'),
        State('navigation-state', 'data'),
        State('history-stack', 'data'),
        prevent_initial_call=True
    )
    def drill_into_cluster(n_clicks, selection, papers, clusters,
                           resolution, use_topics, nav_state, history):
        from papersift.ui.utils.data_loader import (
            cluster_papers,
            papers_to_cytoscape_elements,
            papers_to_table_data,
            generate_cluster_colors,
            compute_paper_embedding,
        )
        from papersift.embedding import sub_cluster
        from papersift.ui.components.breadcrumb import create_breadcrumb

        if not selection or not selection.get('selected_dois'):
            return (no_update,) * 10

        selected_dois = set(selection['selected_dois'])

        # Determine cluster(s) of selected papers
        selected_clusters = set()
        for doi in selected_dois:
            cid = clusters.get(doi)
            if cid is not None:
                selected_clusters.add(str(cid))

        if len(selected_clusters) != 1:
            # Multi-cluster selection - can't drill
            return (no_update,) * 10

        cluster_id = next(iter(selected_clusters))
        # Try int conversion for matching
        try:
            cluster_id_typed = int(cluster_id)
            if any(v == cluster_id_typed for v in clusters.values()):
                cluster_id = cluster_id_typed
        except ValueError:
            pass

        # Save checkpoint before drill
        checkpoint = {
            'dois': [p['doi'] for p in papers],
            'clusters': dict(clusters),
            'navigation_path': list(nav_state.get('path', [])),
            'resolution': resolution,
            'action': 'drill-down',
            'description': f'Before drilling into cluster {cluster_id}',
        }
        history = _push_checkpoint(history, checkpoint)

        # Sub-cluster
        try:
            sub_results = sub_cluster(
                papers, cluster_id, clusters,
                resolution=resolution, use_topics=bool(use_topics)
            )
        except ValueError:
            return (no_update,) * 10

        # Merge sub-clusters into full cluster mapping
        new_clusters = dict(clusters)
        new_clusters.update(sub_results)

        # Filter papers to just the drilled cluster
        member_dois = set(sub_results.keys())
        drilled_papers = [p for p in papers if p['doi'] in member_dois]

        if len(drilled_papers) < 2:
            return (no_update,) * 10

        # Use sub-cluster results only for the drilled papers
        drilled_clusters = sub_results

        # Rebuild visualization
        clusters_rebuilt, builder = cluster_papers(drilled_papers, resolution=resolution, use_topics=bool(use_topics))
        # Use the sub-cluster IDs, not the rebuilt ones
        elements = papers_to_cytoscape_elements(drilled_papers, drilled_clusters, builder)
        rows = papers_to_table_data(drilled_papers, drilled_clusters)
        colors = generate_cluster_colors(set(drilled_clusters.values()))
        embedding = compute_paper_embedding(drilled_papers, method="tsne", use_topics=bool(use_topics))

        # Update navigation
        path = list(nav_state.get('path', []))
        path.append(str(cluster_id))
        new_nav = {'path': path, 'cluster_id': str(cluster_id)}

        breadcrumb = create_breadcrumb(path)

        return (drilled_papers, drilled_clusters, elements, rows, colors,
                {'selected_dois': [], 'source': 'reset'}, embedding,
                new_nav, history, breadcrumb)

    # Back (Up Level)
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
        Output('breadcrumb-container', 'children', allow_duplicate=True),
        Input('drill-up-btn', 'n_clicks'),
        State('navigation-state', 'data'),
        State('history-stack', 'data'),
        State('original-papers', 'data'),
        State('resolution-slider', 'value'),
        State('use-topics-flag', 'data'),
        prevent_initial_call=True
    )
    def drill_up(n_clicks, nav_state, history, original_papers, resolution, use_topics):
        from papersift.ui.utils.data_loader import (
            cluster_papers,
            papers_to_cytoscape_elements,
            papers_to_table_data,
            generate_cluster_colors,
            compute_paper_embedding,
        )
        from papersift.ui.components.breadcrumb import create_breadcrumb

        path = nav_state.get('path', [])
        if not path:
            return (no_update,) * 10

        # Try to restore from history checkpoint
        checkpoints = history.get('checkpoints', [])
        if checkpoints:
            # Find the most recent checkpoint
            cp = checkpoints[-1]
            restored_dois = set(cp['dois'])
            restored_papers = [p for p in original_papers if p['doi'] in restored_dois]
            restored_clusters = cp['clusters']

            if restored_papers and len(restored_papers) >= 2:
                clusters_rebuilt, builder = cluster_papers(
                    restored_papers, resolution=resolution, use_topics=bool(use_topics)
                )
                # Use restored clusters
                elements = papers_to_cytoscape_elements(restored_papers, restored_clusters, builder)
                rows = papers_to_table_data(restored_papers, restored_clusters)
                colors = generate_cluster_colors(set(restored_clusters.values()))
                embedding = compute_paper_embedding(restored_papers, method="tsne", use_topics=bool(use_topics))

                restored_path = cp.get('navigation_path', [])
                new_nav = {'path': restored_path, 'cluster_id': restored_path[-1] if restored_path else None}
                breadcrumb = create_breadcrumb(restored_path)

                # Pop the checkpoint
                new_history = dict(history)
                new_history['checkpoints'] = checkpoints[:-1]
                new_history['current_index'] = len(checkpoints) - 2

                return (restored_papers, restored_clusters, elements, rows, colors,
                        {'selected_dois': [], 'source': 'reset'}, embedding,
                        new_nav, new_history, breadcrumb)

        # Fallback: go to root
        clusters_rebuilt, builder = cluster_papers(
            original_papers, resolution=resolution, use_topics=bool(use_topics)
        )
        elements = papers_to_cytoscape_elements(original_papers, clusters_rebuilt, builder)
        rows = papers_to_table_data(original_papers, clusters_rebuilt)
        colors = generate_cluster_colors(set(clusters_rebuilt.values()))
        embedding = compute_paper_embedding(original_papers, method="tsne", use_topics=bool(use_topics))

        new_nav = {'path': [], 'cluster_id': None}
        breadcrumb = create_breadcrumb([])

        return (original_papers, clusters_rebuilt, elements, rows, colors,
                {'selected_dois': [], 'source': 'reset'}, embedding,
                new_nav, history, breadcrumb)

    # Update breadcrumb on navigation state change
    @app.callback(
        Output('breadcrumb-container', 'children'),
        Input('navigation-state', 'data'),
        prevent_initial_call=True
    )
    def update_breadcrumb(nav_state):
        from papersift.ui.components.breadcrumb import create_breadcrumb
        path = nav_state.get('path', [])
        return create_breadcrumb(path)


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
