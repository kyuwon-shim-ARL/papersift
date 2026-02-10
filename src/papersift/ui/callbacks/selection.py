"""Bidirectional selection synchronization between network and table."""

from dash import callback, Input, Output, State, ctx, no_update, html


def register_selection_callbacks(app):
    """Register all selection-related callbacks."""

    # Network selection -> Store
    @app.callback(
        Output('selection-store', 'data', allow_duplicate=True),
        Input('cytoscape-network', 'selectedNodeData'),
        prevent_initial_call=True
    )
    def network_to_store(selected_nodes):
        if selected_nodes is None:
            return {'selected_dois': [], 'source': 'network'}
        dois = [node['id'] for node in selected_nodes]
        return {'selected_dois': dois, 'source': 'network'}

    # Table selection -> Store
    @app.callback(
        Output('selection-store', 'data', allow_duplicate=True),
        Input('paper-table', 'selectedRows'),
        prevent_initial_call=True
    )
    def table_to_store(selected_rows):
        if selected_rows is None:
            return {'selected_dois': [], 'source': 'table'}
        dois = [row['doi'] for row in selected_rows]
        return {'selected_dois': dois, 'source': 'table'}

    # Store -> Network highlight (only if source is table)
    @app.callback(
        Output('cytoscape-network', 'stylesheet'),
        Input('selection-store', 'data'),
    )
    def store_to_network(selection):
        from papersift.ui.components.network import get_default_stylesheet, get_highlight_stylesheet

        if selection is None or selection.get('source') == 'network':
            # Don't update if network triggered this
            return no_update

        base = get_default_stylesheet()
        selected_dois = selection.get('selected_dois', [])
        return get_highlight_stylesheet(base, selected_dois)

    # Store -> Table selection (only if source is network)
    @app.callback(
        Output('paper-table', 'selectedRows'),
        Input('selection-store', 'data'),
        State('paper-table', 'rowData'),
    )
    def store_to_table(selection, row_data):
        if selection is None or selection.get('source') == 'table':
            # Don't update if table triggered this
            return no_update

        selected_dois = set(selection.get('selected_dois', []))
        # Return the full row objects that should be selected
        return [row for row in (row_data or []) if row['doi'] in selected_dois]

    # Update statistics
    @app.callback(
        Output('stats-display', 'children'),
        Input('selection-store', 'data'),
        State('papers-data', 'data'),
        State('cluster-data', 'data'),
    )
    def update_stats(selection, papers, clusters):
        total = len(papers) if papers else 0
        num_clusters = len(set(clusters.values())) if clusters else 0
        selected = len(selection.get('selected_dois', [])) if selection else 0

        return [
            html.P(f'Total papers: {total}'),
            html.P(f'Clusters: {num_clusters}'),
            html.P(f'Selected: {selected}'),
        ]
