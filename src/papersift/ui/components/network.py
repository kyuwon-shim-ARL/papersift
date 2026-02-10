"""Cytoscape network visualization component."""

import dash_cytoscape as cyto
from dash import html


def create_network_component(elements: list, stylesheet: list = None) -> html.Div:
    """
    Create Cytoscape network component with box selection enabled.

    Args:
        elements: List of node/edge elements
        stylesheet: Optional custom stylesheet

    Returns:
        Dash Div containing the Cytoscape component
    """
    if stylesheet is None:
        stylesheet = get_default_stylesheet()

    return html.Div([
        cyto.Cytoscape(
            id='cytoscape-network',
            elements=elements,
            stylesheet=stylesheet,
            layout={
                'name': 'cose',
                'animate': False,
                'nodeRepulsion': 8000,
                'idealEdgeLength': 100,
                'edgeElasticity': 100,
                'nestingFactor': 0.1,
                'gravity': 0.25,
                'numIter': 500,
                'initialTemp': 200,
                'coolingFactor': 0.95,
                'minTemp': 1.0,
            },
            style={
                'width': '100%',
                'height': '600px',
                'border': '1px solid #ccc'
            },
            # Enable box selection
            boxSelectionEnabled=True,
            # Enable multi-select with Ctrl/Cmd
            userZoomingEnabled=True,
            userPanningEnabled=True,
            autoRefreshLayout=False,
        ),
        html.Div(id='network-info', style={'marginTop': '10px'})
    ], style={'flex': '1', 'minWidth': '400px'})


def get_default_stylesheet() -> list:
    """
    Get default stylesheet for Cytoscape.

    Nodes are colored by cluster, edges are gray.
    Selected nodes have a thick border.
    """
    return [
        # Base node style
        {
            'selector': 'node',
            'style': {
                'label': 'data(label)',
                'background-color': 'data(color)',
                'width': 20,
                'height': 20,
                'font-size': '8px',
                'text-valign': 'bottom',
                'text-halign': 'center',
                'text-wrap': 'ellipsis',
                'text-max-width': '80px',
            }
        },
        # Selected node style
        {
            'selector': 'node:selected',
            'style': {
                'border-width': 3,
                'border-color': '#000',
                'width': 30,
                'height': 30,
            }
        },
        # Base edge style
        {
            'selector': 'edge',
            'style': {
                'width': 'mapData(weight, 1, 10, 1, 4)',
                'line-color': '#ccc',
                'curve-style': 'bezier',
                'opacity': 0.6
            }
        },
    ]


def _escape_doi_for_selector(doi: str) -> str:
    """Escape DOI for use in CSS selector."""
    # Escape backslash first, then other special chars
    result = doi
    for char in ['\\', '"', "'", '[', ']', '/', '.', ':']:
        result = result.replace(char, f'\\{char}')
    return result


def get_highlight_stylesheet(
    base_stylesheet: list,
    selected_dois: list,
) -> list:
    """
    Generate stylesheet with selected nodes highlighted.

    Args:
        base_stylesheet: Default stylesheet
        selected_dois: List of selected DOIs

    Returns:
        Updated stylesheet
    """
    stylesheet = base_stylesheet.copy()

    # Add highlight rules for selected nodes
    for doi in selected_dois:
        escaped_doi = _escape_doi_for_selector(doi)
        stylesheet.append({
            'selector': f'node[id = "{escaped_doi}"]',
            'style': {
                'border-width': 3,
                'border-color': '#ff0000',
                'width': 30,
                'height': 30,
            }
        })

    return stylesheet
