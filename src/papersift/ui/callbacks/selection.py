"""Bidirectional selection synchronization between network and table."""

from dash import callback, Input, Output, State, ctx, no_update, html


def register_selection_callbacks(app):
    """Register all selection-related callbacks."""

    # Bubble chart click -> Store (selects all papers in clicked cluster)
    @app.callback(
        Output('selection-store', 'data', allow_duplicate=True),
        Input('cluster-bubble-chart', 'clickData'),
        State('cluster-data', 'data'),
        prevent_initial_call=True
    )
    def bubble_to_store(click_data, clusters):
        if not click_data or not click_data.get('points'):
            return {'selected_dois': [], 'source': 'network'}

        point = click_data['points'][0]
        # Get the cluster ID from the trace name
        trace_name = point.get('text', '')
        # Extract cluster id - "C{id}"
        cid_str = trace_name.replace('C', '')

        # Find all DOIs in this cluster
        try:
            cid = int(cid_str)
        except ValueError:
            cid = cid_str

        dois = [doi for doi, c in clusters.items() if str(c) == str(cid)]
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

    # Landscape lasso/box selection -> Store
    @app.callback(
        Output('selection-store', 'data', allow_duplicate=True),
        Input('landscape-scatter', 'selectedData'),
        prevent_initial_call=True
    )
    def landscape_to_store(selected_data):
        if not selected_data or not selected_data.get('points'):
            return no_update

        dois = []
        for point in selected_data['points']:
            if 'customdata' in point:
                dois.append(point['customdata'])

        if not dois:
            return no_update

        return {'selected_dois': dois, 'source': 'landscape'}

    # Note: Bubble chart doesn't need store->network sync (removed old Cytoscape stylesheet callback)

    # Store -> Table selection (only if source is network or landscape)
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
