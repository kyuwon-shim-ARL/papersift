"""Export PaperSift network as standalone interactive HTML."""

import plotly.graph_objects as go
import networkx as nx
from pathlib import Path

from papersift.ui.utils.data_loader import (
    load_papers,
    cluster_papers,
    generate_cluster_colors,
)


def export_network_html(
    papers_path: str,
    output_path: str,
    resolution: float = 1.0,
    mode: str = "cluster",
) -> None:
    """
    Export paper network as standalone interactive HTML.

    Args:
        papers_path: Path to papers JSON
        output_path: Output HTML file path
        resolution: Leiden clustering resolution
        mode: Visualization mode ("cluster" or "paper")
    """
    # Load and cluster
    papers = load_papers(papers_path)
    clusters, builder = cluster_papers(papers, resolution=resolution)
    colors = generate_cluster_colors(len(set(clusters.values())))

    if mode == "cluster":
        summaries = builder.get_cluster_summary(clusters)
        fig = _create_cluster_view_figure(summaries, builder, papers, colors)
    else:
        # Paper mode (original)
        G = _build_networkx_graph(papers, clusters, builder, colors)
        fig = _create_plotly_figure(G, papers)

    # Export as self-contained HTML
    fig.write_html(
        output_path,
        include_plotlyjs=True,
        full_html=True,
        config={'displayModeBar': True, 'scrollZoom': True}
    )

    print(f"Exported: {output_path} (mode: {mode})")
    print("Note: This is a static snapshot. Filtering and re-clustering are not available.")


def _build_networkx_graph(papers, clusters, builder, colors):
    """Convert PaperSift graph to NetworkX."""
    G = nx.Graph()

    # Add nodes
    doi_to_title = {p['doi']: p.get('title', p['doi']) for p in papers}
    for doi, cluster_id in clusters.items():
        G.add_node(
            doi,
            title=doi_to_title.get(doi, doi),
            cluster=cluster_id,
            color=colors[cluster_id % len(colors)],
        )

    # Add edges from builder.graph (igraph)
    # NOTE: EntityLayerBuilder uses 'doi' attribute, not 'name'
    # Reference: entity_layer.py:323, data_loader.py:135-136
    for edge in builder.graph.es:
        source = builder.graph.vs[edge.source]['doi']
        target = builder.graph.vs[edge.target]['doi']
        weight = edge['weight'] if 'weight' in edge.attributes() else 1
        if source in clusters and target in clusters:
            G.add_edge(source, target, weight=weight)

    return G


def _compute_cluster_edges(summaries, builder):
    """Compute edges between clusters based on shared entities."""
    cluster_entities = {}
    for summary in summaries:
        cid = summary['cluster_id']
        entities = set()
        for doi in summary['dois']:
            entities |= builder._paper_entities.get(doi, set())
        cluster_entities[cid] = entities

    edges = []
    cluster_ids = list(cluster_entities.keys())
    for i, cid_a in enumerate(cluster_ids):
        for cid_b in cluster_ids[i+1:]:
            shared = cluster_entities[cid_a] & cluster_entities[cid_b]
            if len(shared) >= 2:
                edges.append((cid_a, cid_b, len(shared)))

    return edges


def _create_cluster_view_figure(summaries, builder, papers, colors):
    """Create Plotly figure with cluster-level nodes."""
    G = nx.Graph()

    # Build DOI-to-title map
    doi_to_title = {p['doi']: p.get('title', p['doi']) for p in papers}

    # Add cluster nodes
    for s in summaries:
        cid = s['cluster_id']
        # Sample papers (first 3)
        sample_titles = []
        for doi in s['dois'][:3]:
            title = doi_to_title.get(doi, doi)
            sample_titles.append(title[:60])

        hover = (
            f"<b>Cluster {cid + 1}</b> ({s['size']} papers)<br>"
            f"<br>Top Entities: {', '.join(s['top_entities'][:5])}<br>"
            f"<br>Sample Papers:<br>"
            + "<br>".join(f"- {t}" for t in sample_titles)
        )

        G.add_node(
            cid,
            size=s['size'],
            color=colors[cid % len(colors)],
            hover=hover,
        )

    # Add inter-cluster edges
    edges = _compute_cluster_edges(summaries, builder)
    for cid_a, cid_b, weight in edges:
        G.add_edge(cid_a, cid_b, weight=weight)

    # Layout
    pos = nx.spring_layout(G, k=1.5, iterations=50, seed=42)

    # Edge traces
    edge_x, edge_y = [], []
    for u, v in G.edges():
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])

    edge_trace = go.Scatter(
        x=edge_x, y=edge_y,
        mode='lines',
        line=dict(width=0.5, color='#ccc'),
        hoverinfo='none'
    )

    # Node traces
    node_x = [pos[n][0] for n in G.nodes()]
    node_y = [pos[n][1] for n in G.nodes()]
    node_sizes = [10 + G.nodes[n]['size'] * 3 for n in G.nodes()]
    node_colors = [G.nodes[n]['color'] for n in G.nodes()]
    node_text = [G.nodes[n]['hover'] for n in G.nodes()]
    node_labels = [f"C{n+1}" for n in G.nodes()]

    node_trace = go.Scatter(
        x=node_x, y=node_y,
        mode='markers+text',
        marker=dict(size=node_sizes, color=node_colors,
                    line=dict(width=1, color='white')),
        text=node_labels,
        textposition='middle center',
        textfont=dict(size=8, color='white'),
        hovertext=node_text,
        hoverinfo='text',
        name='Clusters'
    )

    fig = go.Figure(
        data=[edge_trace, node_trace],
        layout=go.Layout(
            title='PaperSift Cluster View (Static Snapshot)',
            showlegend=False,
            hovermode='closest',
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[-1.5, 1.5]),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[-1.5, 1.5]),
            dragmode='pan',
        )
    )

    return fig


def _create_plotly_figure(G: nx.Graph, papers: list) -> go.Figure:
    """Create Plotly figure from NetworkX graph."""
    # Layout
    pos = nx.spring_layout(G, k=0.5, iterations=50, seed=42)

    # Edge traces
    edge_x, edge_y = [], []
    for u, v in G.edges():
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])

    edge_trace = go.Scatter(
        x=edge_x, y=edge_y,
        mode='lines',
        line=dict(width=0.5, color='#ccc'),
        hoverinfo='none'
    )

    # Node traces (grouped by cluster for coloring)
    node_traces = []
    cluster_nodes = {}
    for node in G.nodes():
        cluster = G.nodes[node]['cluster']
        if cluster not in cluster_nodes:
            cluster_nodes[cluster] = {'x': [], 'y': [], 'text': [], 'color': G.nodes[node]['color']}
        x, y = pos[node]
        cluster_nodes[cluster]['x'].append(x)
        cluster_nodes[cluster]['y'].append(y)
        title = G.nodes[node]['title'][:50] + '...' if len(G.nodes[node]['title']) > 50 else G.nodes[node]['title']
        cluster_nodes[cluster]['text'].append(f"<b>{title}</b><br>DOI: {node}<br>Cluster: {cluster}")

    for cluster_id, data in cluster_nodes.items():
        node_traces.append(go.Scatter(
            x=data['x'], y=data['y'],
            mode='markers',
            marker=dict(size=10, color=data['color'], line=dict(width=1, color='white')),
            text=data['text'],
            hoverinfo='text',
            name=f'Cluster {cluster_id}'
        ))

    # Figure
    fig = go.Figure(
        data=[edge_trace] + node_traces,
        layout=go.Layout(
            title='PaperSift Network (Static Snapshot)',
            showlegend=True,
            hovermode='closest',
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[-1.5, 1.5]),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[-1.5, 1.5]),
            dragmode='pan',
        )
    )

    return fig
