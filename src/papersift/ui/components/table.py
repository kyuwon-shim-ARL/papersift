"""AG Grid table component for paper list."""

import dash_ag_grid as dag
from dash import html


def create_table_component(row_data: list) -> html.Div:
    """
    Create AG Grid table with multi-select enabled.

    Args:
        row_data: List of row dictionaries

    Returns:
        Dash Div containing the AG Grid component
    """
    column_defs = [
        {
            'headerName': '',
            'field': 'cluster_color',
            'width': 30,
            'cellStyle': {
                'function': "{'backgroundColor': params.value}"
            },
            'headerCheckboxSelection': True,
            'checkboxSelection': True,
        },
        {
            'headerName': 'Cluster',
            'field': 'cluster',
            'width': 80,
            'filter': 'agNumberColumnFilter',
            'sortable': True,
        },
        {
            'headerName': 'Year',
            'field': 'year',
            'width': 70,
            'filter': 'agNumberColumnFilter',
            'sortable': True,
        },
        {
            'headerName': 'Title',
            'field': 'title',
            'flex': 1,
            'filter': 'agTextColumnFilter',
            'sortable': True,
            'tooltipField': 'title',
        },
        {
            'headerName': 'DOI',
            'field': 'doi',
            'width': 200,
            'filter': 'agTextColumnFilter',
        },
    ]

    return html.Div([
        dag.AgGrid(
            id='paper-table',
            rowData=row_data,
            columnDefs=column_defs,
            getRowId="params.data.doi",  # Use DOI as row ID for reliable selection with pagination
            defaultColDef={
                'resizable': True,
                'sortable': True,
                'filter': True,
            },
            dashGridOptions={
                'rowSelection': 'multiple',
                'suppressRowClickSelection': False,
                'rowMultiSelectWithClick': True,
                'animateRows': False,
                'pagination': True,
                'paginationPageSize': 50,
                'enableCellTextSelection': True,
                'suppressRowDeselection': False,
            },
            style={'height': '600px'},
            className='ag-theme-alpine',
        ),
        html.Div(id='table-info', style={'marginTop': '10px'})
    ], style={'flex': '1', 'minWidth': '400px'})


