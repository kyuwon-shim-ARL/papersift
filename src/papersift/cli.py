#!/usr/bin/env python3
"""PaperSift CLI: Entity-based paper clustering and exploration."""

import argparse
import json
import os
import sys
from pathlib import Path

from papersift.doi import normalize_doi


def main():
    parser = argparse.ArgumentParser(
        description="PaperSift: Entity-based paper clustering",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic clustering (Title-only entities)
  papersift cluster papers.json -o results/

  # Enhanced clustering with OpenAlex Topics
  papersift cluster papers_enriched.json -o results/ --use-topics

  # With citation validation
  papersift cluster papers.json -o results/ --validate

  # Find hub papers (highest entity connectivity)
  papersift find papers.json --hubs 10

  # Find papers by entity
  papersift find papers.json --entity "transformer"

  # Enrich papers with OpenAlex referenced_works
  papersift enrich papers.json -o enriched.json --email user@example.com

  # Stream from seed paper
  papersift stream papers.json --seed "https://doi.org/10.1101/..." --hops 5
        """
    )

    parser.add_argument(
        "--data-dir",
        default="data/papers",
        help="Base directory for paper storage (default: data/papers)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # ===== cluster command =====
    cluster_parser = subparsers.add_parser(
        "cluster",
        help="Cluster papers by shared entities"
    )
    cluster_parser.add_argument("input", help="Papers JSON file")
    cluster_parser.add_argument("-o", "--output", required=True, help="Output directory")
    cluster_parser.add_argument("--resolution", type=float, default=1.0)
    cluster_parser.add_argument("--seed", type=int, default=42)
    cluster_parser.add_argument("--validate", action="store_true")
    cluster_parser.add_argument("--use-topics", action="store_true",
                                help="Use OpenAlex topics as additional entities (requires enriched data)")

    # ===== enrich command =====
    enrich_parser = subparsers.add_parser(
        "enrich",
        help="Enrich papers with OpenAlex data (referenced_works, topics, abstract)"
    )
    enrich_parser.add_argument("input", help="Papers JSON file")
    enrich_parser.add_argument("-o", "--output", required=True, help="Output JSON file")
    enrich_parser.add_argument("--email", required=True,
                               help="Email for OpenAlex polite pool (faster rate limits)")
    enrich_parser.add_argument("--fields", default="referenced_works,openalex_id",
                               help="Comma-separated fields to fetch (default: referenced_works,openalex_id)")

    # ===== find command (NEW) =====
    find_parser = subparsers.add_parser(
        "find",
        help="Find papers by entity or discover hub papers"
    )
    find_parser.add_argument("input", help="Papers JSON file")
    find_parser.add_argument("--entity", help="Find papers containing this entity")
    find_parser.add_argument("--hubs", type=int, help="Find top N hub papers")
    find_parser.add_argument("--format", choices=["table", "json"], default="table")
    find_parser.add_argument("--use-topics", action="store_true",
                             help="Use OpenAlex topics as additional entities")

    # ===== stream command (NEW) =====
    stream_parser = subparsers.add_parser(
        "stream",
        help="Follow entity connections from a seed paper"
    )
    stream_parser.add_argument("input", help="Papers JSON file")
    stream_parser.add_argument("--seed", required=True, help="Starting paper DOI")
    stream_parser.add_argument("--hops", type=int, default=5, help="Max hops to follow")
    stream_parser.add_argument("--strategy", choices=["strongest", "diverse"], default="strongest")
    stream_parser.add_argument("--expand", action="store_true", help="Use expand mode (all neighbors) instead of stream")
    stream_parser.add_argument("--use-topics", action="store_true",
                               help="Use OpenAlex topics as additional entities")
    stream_parser.add_argument("--format", choices=["table", "json"], default="table",
                               help="Output format (default: table)")

    # ===== ui command (NEW) =====
    ui_parser = subparsers.add_parser(
        "ui",
        help="Launch interactive UI for paper filtering"
    )
    ui_parser.add_argument("input", help="Papers JSON file")
    ui_parser.add_argument("--port", type=int, default=8050, help="Server port")
    ui_parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    ui_parser.add_argument("--host", default="127.0.0.1",
                           help="Server host (use 0.0.0.0 for external access)")
    ui_parser.add_argument("--export", metavar="FILE",
                           help="Export interactive HTML (static snapshot, no server)")
    ui_parser.add_argument("--mode", choices=["cluster", "paper"], default="cluster",
                           help="Export visualization mode: cluster (default) or paper")
    ui_parser.add_argument("--use-topics", action="store_true",
                           help="Use OpenAlex topics for enhanced clustering (requires enriched data)")
    ui_parser.add_argument("--analysis-dir", metavar="DIR",
                           help="Directory with analysis JSON files (method_flows.json, trend_analysis.json, hypotheses.json)")

    # ===== browse command (NEW) =====
    browse_parser = subparsers.add_parser(
        "browse",
        help="Browse cluster contents (text-based)"
    )
    browse_parser.add_argument("input", help="Papers JSON file")
    browse_parser.add_argument("--list", action="store_true",
                               help="List all clusters with summary")
    browse_parser.add_argument("--cluster", type=str,
                               help="Show specific cluster(s), comma-separated IDs")
    browse_parser.add_argument("--export", metavar="FILE",
                               help="Export selected clusters to JSON")
    browse_parser.add_argument("--full", action="store_true",
                               help="Show all DOIs (default: first 10)")
    browse_parser.add_argument("--use-topics", action="store_true",
                               help="Use OpenAlex topics as additional entities")
    browse_parser.add_argument("--resolution", type=float, default=1.0,
                               help="Leiden clustering resolution (default: 1.0)")
    browse_parser.add_argument("--format", choices=["table", "json"], default="table",
                               help="Output format (default: table)")
    browse_parser.add_argument("--sub-cluster", type=str, metavar="CLUSTER_ID",
                               help="Sub-cluster a specific cluster (e.g., '3' or '3.1')")
    browse_parser.add_argument("--sub-resolution", type=float, default=1.0,
                               help="Resolution for sub-clustering (default: 1.0)")

    # ===== landscape command (NEW) =====
    landscape_parser = subparsers.add_parser(
        "landscape",
        help="Generate UMAP/t-SNE landscape visualization"
    )
    landscape_parser.add_argument("input", help="Papers JSON file (or '-' for stdin)")
    landscape_parser.add_argument("--method", choices=["umap", "tsne"], default="tsne",
                                   help="Embedding method (default: tsne)")
    landscape_parser.add_argument("-o", "--output", required=True, help="Output HTML file")
    landscape_parser.add_argument("--use-topics", action="store_true",
                                   help="Use OpenAlex topics as additional entities")
    landscape_parser.add_argument("--resolution", type=float, default=1.0,
                                   help="Leiden resolution for cluster coloring (default: 1.0)")
    landscape_parser.add_argument("--seed", type=int, default=42, help="Random seed")
    landscape_parser.add_argument("--interactive", action="store_true",
                                   help="Open in browser after export")

    # ===== filter command (NEW) =====
    filter_parser = subparsers.add_parser(
        "filter",
        help="Filter papers by entity, cluster, or DOI list"
    )
    filter_parser.add_argument("input", help="Papers JSON file (use '-' for stdin)")
    filter_parser.add_argument("--entity", action="append", help="Entity to filter by (repeatable)")
    filter_parser.add_argument("--entity-any", action="store_true",
                               help="OR logic for entities (default: AND)")
    filter_parser.add_argument("--cluster", type=str,
                               help="Cluster IDs to keep (comma-separated, e.g. '3,5')")
    filter_parser.add_argument("--dois", help="File with DOI list to keep (one per line or JSON array)")
    filter_parser.add_argument("--exclude", action="store_true",
                               help="Invert: remove matching papers instead of keeping them")
    filter_parser.add_argument("--clusters-from", help="clusters.json file for cluster-based filtering")
    filter_parser.add_argument("--resolution", type=float, default=1.0)
    filter_parser.add_argument("--use-topics", action="store_true")
    filter_parser.add_argument("--format", choices=["json", "table"], default="json",
                               help="Output format (default: json)")
    filter_parser.add_argument("-o", "--output", help="Output file (default: stdout)")

    # ===== merge command (NEW) =====
    merge_parser = subparsers.add_parser(
        "merge",
        help="Merge multiple paper JSON files, deduplicate by DOI"
    )
    merge_parser.add_argument("inputs", nargs="+", help="Paper JSON files to merge")
    merge_parser.add_argument("-o", "--output", required=True, help="Output file")

    # ===== dedupe command (NEW) =====
    dedupe_parser = subparsers.add_parser(
        "dedupe",
        help="Remove non-paper DOIs (datasets, supplementary) and deduplicate preprints"
    )
    dedupe_parser.add_argument("input", help="Papers JSON file")
    dedupe_parser.add_argument("-o", "--output", required=True, help="Output JSON file")
    dedupe_parser.add_argument("--keep-non-papers", action="store_true",
                               help="Don't remove datasets/supplementary/editorial DOIs")
    dedupe_parser.add_argument("--no-preprint-dedupe", action="store_true",
                               help="Don't deduplicate preprint/published pairs")
    dedupe_parser.add_argument("--report", action="store_true",
                               help="Print detailed report of removed entries")

    # ===== subcluster command (NEW) =====
    subcluster_parser = subparsers.add_parser(
        "subcluster",
        help="Sub-cluster a specific cluster"
    )
    subcluster_parser.add_argument("input", help="Papers JSON file (use '-' for stdin)")
    subcluster_parser.add_argument("--cluster", required=True, type=str,
                                    help="Cluster ID to subdivide (e.g., '3' or '3.1')")
    subcluster_parser.add_argument("--clusters-from", required=True,
                                    help="Existing clusters.json file")
    subcluster_parser.add_argument("--resolution", type=float, default=1.0)
    subcluster_parser.add_argument("--use-topics", action="store_true")
    subcluster_parser.add_argument("--seed", type=int, default=42)
    subcluster_parser.add_argument("-o", "--output", help="Output directory for updated clusters")
    subcluster_parser.add_argument("--format", choices=["json", "table"], default="table")

    # ===== Pipeline commands (require papersift[pipeline]) =====

    # search command
    search_parser = subparsers.add_parser("search", help="Search papers on OpenAlex")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--max", type=int, default=50, help="Max results")
    search_parser.add_argument("--oa-only", action="store_true", help="Only OA papers")
    search_parser.add_argument("--year-min", type=int, help="Minimum publication year")
    search_parser.add_argument("--email", help="Contact email (or set PAPER_PIPELINE_EMAIL)")
    search_parser.add_argument("--collection", help="Add to collection")
    search_parser.add_argument("--quiet", "-q", action="store_true")
    search_parser.add_argument("--output", "-o", help="Export as flat JSON (for clustering)")

    # fetch command
    fetch_parser = subparsers.add_parser("fetch", help="Fetch paper content (PDF/XML)")
    fetch_parser.add_argument("--doi", help="Single DOI to fetch")
    fetch_parser.add_argument("--collection", help="Fetch all papers in collection")
    fetch_parser.add_argument("--email", help="Contact email")
    fetch_parser.add_argument("--grobid-url", default="http://localhost:8070")

    # status command
    status_parser = subparsers.add_parser("status", help="Show paper store status")

    # collection command
    collection_parser = subparsers.add_parser("collection", help="Manage collections")
    collection_sub = collection_parser.add_subparsers(dest="collection_cmd")
    coll_list = collection_sub.add_parser("list", help="List collections")
    coll_show = collection_sub.add_parser("show", help="Show collection details")
    coll_show.add_argument("name", help="Collection name")
    coll_create = collection_sub.add_parser("create", help="Create collection")
    coll_create.add_argument("name", help="Collection name")
    coll_create.add_argument("--dois", required=True, help="Comma-separated DOIs")
    coll_export = collection_sub.add_parser("export", help="Export collection as flat JSON")
    coll_export.add_argument("name", help="Collection name")
    coll_export.add_argument("-o", "--output", required=True, help="Output JSON path")

    # ===== abstract command =====
    abstract_parser = subparsers.add_parser(
        "abstract",
        help="Fetch abstracts from OpenAlex, Semantic Scholar, and Europe PMC",
        description="Fetch abstracts from 3 APIs: OpenAlex (batch 50) → Semantic Scholar (batch 200) → Europe PMC (individual).",
    )
    abstract_parser.add_argument("input", help="Papers JSON file")
    abstract_parser.add_argument("-o", "--output", required=True,
                                help="Output JSON file (papers with abstracts attached)")
    abstract_parser.add_argument("--email", default="",
                                help="Email for OpenAlex polite pool (faster access)")
    abstract_parser.add_argument("--skip-epmc", action="store_true",
                                help="Skip Europe PMC individual queries (faster but lower coverage)")

    # ===== research command =====
    research_parser = subparsers.add_parser(
        "research",
        help="Full research pipeline: cluster + abstracts + LLM extraction",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Full research pipeline: cluster → fetch abstracts → LLM extraction → enriched output.",
        epilog="""output files:
  clusters.json           Cluster assignments ({doi: cluster_id}) for filter
  enriched_papers.json    Full enriched data (papers + clusters + extractions)
  for_research.md         Self-contained cluster briefing for Claude/LLM analysis
  extraction_prompts.json Raw prompts for reproducibility

workflow: landscape survey
  papersift research papers.json -o results/sweep/

workflow: drill-down (focus on specific clusters)
  papersift browse papers.json --list --clusters-from results/sweep/clusters.json
  papersift filter papers.json --cluster 1,3 --clusters-from results/sweep/clusters.json -o focused.json
  papersift research focused.json -o results/sweep/focused/

workflow: entity-based focus (skip cluster numbers)
  papersift filter papers.json --entity "whole-cell" --entity "ODE" --entity-any -o focused.json
  papersift research focused.json -o results/focused/""",
    )
    research_parser.add_argument("input", help="Papers JSON file")
    research_parser.add_argument("-o", "--output", required=True, help="Output directory")
    research_parser.add_argument("--email", default="", help="Email for OpenAlex polite pool")
    research_parser.add_argument("--resolution", type=float, default=1.0,
                                help="Leiden clustering resolution (default: 1.0)")
    research_parser.add_argument("--seed", type=int, default=42,
                                help="Random seed for reproducible clustering (default: 42)")
    research_parser.add_argument("--use-topics", action="store_true",
                                help="Include OpenAlex topics as entities")
    research_parser.add_argument("--skip-epmc", action="store_true",
                                help="Skip Europe PMC (individual queries, slower)")
    research_parser.add_argument("--clusters-from",
                                help="Pre-computed clusters JSON file ({doi: cluster_id})")
    research_parser.add_argument("--extractions-from",
                                help="Pre-computed LLM extractions JSON file (skips auto-extraction)")
    research_parser.add_argument("--no-llm", action="store_true",
                                help="Skip automatic LLM extraction (save prompts only)")

    args = parser.parse_args()

    if args.command == "cluster":
        run_cluster(args)
    elif args.command == "enrich":
        run_enrich(args)
    elif args.command == "find":
        run_find(args)
    elif args.command == "stream":
        run_stream(args)
    elif args.command == "ui":
        run_ui(args)
    elif args.command == "browse":
        run_browse(args)
    elif args.command == "landscape":
        run_landscape(args)
    elif args.command == "filter":
        run_filter(args)
    elif args.command == "merge":
        run_merge(args)
    elif args.command == "dedupe":
        run_dedupe(args)
    elif args.command == "subcluster":
        run_subcluster(args)
    elif args.command == "abstract":
        run_abstract(args)
    elif args.command == "research":
        run_research(args)
    # Pipeline command dispatch
    elif args.command == "search":
        run_search(args)
    elif args.command == "fetch":
        run_fetch(args)
    elif args.command == "status":
        run_status(args)
    elif args.command == "collection":
        run_collection(args)


def run_enrich(args):
    """Execute enrich command."""
    try:
        from papersift.enrich import OpenAlexEnricher
    except ImportError:
        print("Error: enrichment requires pyalex. Install with: pip install papersift[enrich]",
              file=sys.stderr)
        sys.exit(1)

    papers = load_papers(args.input)
    fields = [f.strip() for f in args.fields.split(',')]

    enricher = OpenAlexEnricher(email=args.email)
    enriched = enricher.enrich_papers(papers, fields=fields)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(enriched, f, indent=2)

    print(f"Saved: {output_path}")


def run_find(args):
    """Execute find command."""
    from papersift import EntityLayerBuilder

    papers = load_papers(args.input)
    use_topics = getattr(args, 'use_topics', False)
    builder = EntityLayerBuilder(use_topics=use_topics)
    builder.build_from_papers(papers)

    if args.hubs:
        hubs = builder.find_hub_papers(top_k=args.hubs)
        if args.format == "json":
            # JSON output
            output = []
            for h in hubs:
                title = get_title(papers, h['doi'])
                output.append({
                    'doi': h['doi'],
                    'title': title,
                    'hub_score': h['hub_score'],
                    'entities': h['entities']
                })
            print(json.dumps(output, indent=2))
        else:
            # Table output (default)
            print(f"Top {args.hubs} Entity Hub Papers:")
            print("-" * 60)
            for i, h in enumerate(hubs, 1):
                title = get_title(papers, h['doi'])
                print(f"{i:2d}. [{h['hub_score']:4d}] {title[:50]}...")
                print(f"    Entities: {', '.join(h['entities'][:5])}")

    elif args.entity:
        dois = builder.find_papers_by_entity(args.entity)
        if args.format == "json":
            # JSON output
            output = []
            for doi in dois:
                title = get_title(papers, doi)
                output.append({'doi': doi, 'title': title})
            print(json.dumps(output, indent=2))
        else:
            # Table output (default)
            print(f"Papers containing '{args.entity}': {len(dois)}")
            for doi in dois[:20]:
                title = get_title(papers, doi)
                print(f"  - {title[:60]}...")
            if len(dois) > 20:
                print(f"  ... and {len(dois) - 20} more")


def run_stream(args):
    """Execute stream command."""
    from papersift import EntityLayerBuilder

    papers = load_papers(args.input)
    use_topics = getattr(args, 'use_topics', False)
    builder = EntityLayerBuilder(use_topics=use_topics)
    builder.build_from_papers(papers)

    if args.expand:
        reachable = builder.expand_from_seed(args.seed, hops=args.hops)
        if args.format == "json":
            # JSON output
            output = []
            for doi in reachable:
                title = get_title(papers, doi)
                output.append({'doi': doi, 'title': title})
            print(json.dumps(output, indent=2))
        else:
            # Table output (default)
            print(f"Papers reachable in {args.hops} hops from seed: {len(reachable)}")
            for doi in list(reachable)[:20]:
                title = get_title(papers, doi)
                print(f"  - {title[:60]}...")
    else:
        path = builder.entity_stream(args.seed, strategy=args.strategy, max_hops=args.hops)
        if args.format == "json":
            # JSON output
            output = []
            for doi in path:
                title = get_title(papers, doi)
                output.append({'doi': doi, 'title': title})
            print(json.dumps(output, indent=2))
        else:
            # Table output (default)
            print(f"Entity stream ({args.strategy}, {len(path)} papers):")
            for i, doi in enumerate(path):
                title = get_title(papers, doi)
                marker = ">" if i == 0 else " "
                print(f"{marker} {i}. {title[:55]}...")


def load_papers(path):
    """Load papers from file or stdin.

    Args:
        path: File path or "-" for stdin

    Returns:
        List of paper dicts
    """
    if path == "-":
        if sys.stdin.isatty():
            print("Error: No input on stdin. Use '-' only when piping data.", file=sys.stderr)
            sys.exit(1)
        try:
            data = json.load(sys.stdin)
        except json.JSONDecodeError:
            print("Error: Invalid JSON input on stdin", file=sys.stderr)
            sys.exit(1)
    else:
        with open(path) as f:
            data = json.load(f)
    papers = data.get('papers', data) if isinstance(data, dict) else data
    # Normalize DOIs
    for p in papers:
        if 'doi' in p:
            p['doi'] = normalize_doi(p['doi'])
        if 'referenced_works' in p:
            p['referenced_works'] = [normalize_doi(ref) for ref in p['referenced_works']]
    return papers


def get_title(papers, doi):
    return next((p['title'] for p in papers if p['doi'] == doi), doi)


def run_cluster(args):
    """Execute clustering command."""
    from papersift import EntityLayerBuilder, ClusterValidator

    # Load papers
    papers = load_papers(args.input)
    print(f"Loaded {len(papers)} papers")

    # Build entity graph and cluster
    use_topics = getattr(args, 'use_topics', False)
    mode = "Title + OpenAlex Topics" if use_topics else "Title-only"
    print(f"Building entity graph ({mode})...")
    builder = EntityLayerBuilder(use_topics=use_topics)
    builder.build_from_papers(papers)
    print(f"  Graph: {builder.graph.vcount()} nodes, {builder.graph.ecount()} edges")

    print(f"Running Leiden clustering (resolution={args.resolution}, seed={args.seed})...")
    clusters = builder.run_leiden(resolution=args.resolution, seed=args.seed)
    num_clusters = len(set(clusters.values()))
    print(f"  Found {num_clusters} clusters")

    # Generate summaries
    summaries = builder.get_cluster_summary(clusters)

    # Create output directory
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save outputs
    clusters_path = output_dir / "clusters.json"
    with open(clusters_path, 'w') as f:
        json.dump(clusters, f, indent=2)
    print(f"Saved: {clusters_path}")

    summaries_path = output_dir / "communities.json"
    with open(summaries_path, 'w') as f:
        json.dump(summaries, f, indent=2)
    print(f"Saved: {summaries_path}")

    # Validation (if requested)
    if args.validate:
        print(f"\nValidating with citation data...")
        validator = ClusterValidator(clusters, papers)

        if not validator.has_citation_data():
            print("  Warning: Insufficient citation data for validation")
        else:
            report = validator.generate_report()
            print(f"  ARI: {report.ari:.3f}")
            print(f"  NMI: {report.nmi:.3f}")
            print(f"  Confidence: {report.confidence_summary}")
            print(f"  {report.interpretation}")

            # Save validation report
            report_path = output_dir / "validation_report.json"
            with open(report_path, 'w') as f:
                json.dump({
                    'ari': report.ari,
                    'nmi': report.nmi,
                    'num_papers': report.num_papers,
                    'num_entity_clusters': report.num_entity_clusters,
                    'num_citation_clusters': report.num_citation_clusters,
                    'confidence_summary': report.confidence_summary,
                    'interpretation': report.interpretation
                }, f, indent=2)
            print(f"Saved: {report_path}")

            # Save confidence scores
            confidence_path = output_dir / "confidence.json"
            with open(confidence_path, 'w') as f:
                json.dump(report.confidence_scores, f, indent=2)
            print(f"Saved: {confidence_path}")


def run_ui(args):
    """Launch interactive UI or export static HTML."""
    # Mutual exclusion check
    if args.export and args.host != "127.0.0.1":
        print("Error: --export and --host cannot be used together.", file=sys.stderr)
        print("  --export generates a static file, no server is started.", file=sys.stderr)
        sys.exit(1)

    if args.export:
        # Export mode
        from papersift.ui.exporter import export_network_html
        export_network_html(args.input, args.export, mode=getattr(args, 'mode', 'cluster'))
    else:
        # Server mode
        try:
            from papersift.ui.app import run_server
        except ImportError:
            print("Error: UI requires additional dependencies. Install with: pip install -r requirements-ui.txt",
                  file=sys.stderr)
            sys.exit(1)

        run_server(args.input, port=args.port, debug=args.debug, host=args.host,
                   use_topics=getattr(args, 'use_topics', False),
                   analysis_dir=getattr(args, 'analysis_dir', None))


def run_browse(args):
    """Browse cluster contents in text mode."""
    from papersift import EntityLayerBuilder

    papers = load_papers(args.input)
    use_topics = getattr(args, 'use_topics', False)
    builder = EntityLayerBuilder(use_topics=use_topics)
    builder.build_from_papers(papers)

    clusters = builder.run_leiden(resolution=args.resolution, seed=42)
    summaries = builder.get_cluster_summary(clusters)
    # Sort by size descending
    summaries.sort(key=lambda s: s['size'], reverse=True)

    # Default to --list if no specific action
    if not args.cluster and not args.export:
        args.list = True

    if args.list:
        _browse_list(summaries, len(papers), args.format)

    if args.cluster:
        cluster_ids = [int(x.strip()) for x in args.cluster.split(',')]
        _browse_detail(summaries, cluster_ids, papers, args.full, args.format)

        if args.export:
            _browse_export(summaries, cluster_ids, papers, args.export)

    if getattr(args, 'sub_cluster', None):
        from papersift.embedding import sub_cluster
        target_cid = args.sub_cluster
        # Try to match cluster_id (could be int or string)
        try:
            target_cid_int = int(target_cid)
            if target_cid_int in set(clusters.values()):
                target_cid = target_cid_int
        except ValueError:
            pass  # Keep as string for hierarchical IDs like "3.1"

        try:
            sub_results = sub_cluster(
                papers, target_cid, clusters,
                resolution=getattr(args, 'sub_resolution', 1.0),
                seed=42, use_topics=use_topics
            )
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

        # Build summaries for sub-clusters
        sub_builder = EntityLayerBuilder(use_topics=use_topics)
        subset = [p for p in papers if p['doi'] in sub_results]
        sub_builder.build_from_papers(subset)
        sub_summaries = sub_builder.get_cluster_summary(sub_results)
        sub_summaries.sort(key=lambda s: s['size'], reverse=True)

        if args.format == "json":
            output = []
            for s in sub_summaries:
                output.append({
                    'cluster_id': s['cluster_id'],
                    'size': s['size'],
                    'top_entities': s['top_entities']
                })
            print(json.dumps(output, indent=2))
        else:
            n_papers = sum(s['size'] for s in sub_summaries)
            print(f"\nSub-clusters of cluster {args.sub_cluster} ({n_papers} papers):\n")
            for s in sub_summaries:
                entities = ', '.join(s['top_entities'][:5])
                print(f"  Sub-cluster {s['cluster_id']} ({s['size']} papers): {entities}")


def _browse_list(summaries, total_papers, format_type="table"):
    """Print cluster list summary."""
    if format_type == "json":
        # JSON output
        output = []
        for s in summaries:
            output.append({
                'cluster_id': s['cluster_id'],
                'size': s['size'],
                'top_entities': s['top_entities']
            })
        print(json.dumps(output, indent=2))
    else:
        # Table output (default)
        print(f"{len(summaries)} clusters found ({total_papers} papers total)\n")
        for s in summaries:
            entities = ', '.join(s['top_entities'][:5])
            print(f"Cluster {s['cluster_id']} ({s['size']} papers): {entities}")


def _browse_detail(summaries, cluster_ids, papers, full=False, format_type="table"):
    """Print detailed cluster info."""
    summary_map = {s['cluster_id']: s for s in summaries}

    if format_type == "json":
        # JSON output
        output = []
        for cid in cluster_ids:
            if cid not in summary_map:
                continue
            s = summary_map[cid]
            # Get sample papers with details
            sample_papers = []
            for doi in s['dois'][:3]:
                title = get_title(papers, doi)
                year = next((p.get('year', '?') for p in papers if p['doi'] == doi), '?')
                sample_papers.append({'doi': doi, 'title': title, 'year': year})

            output.append({
                'cluster_id': cid,
                'size': s['size'],
                'top_entities': s['top_entities'],
                'sample_papers': sample_papers,
                'dois': s['dois'] if full else s['dois'][:10]
            })
        print(json.dumps(output, indent=2))
    else:
        # Table output (default)
        for cid in cluster_ids:
            if cid not in summary_map:
                print(f"Cluster {cid}: not found", file=sys.stderr)
                continue
            s = summary_map[cid]
            print(f"\nCluster {cid}: {s['size']} papers")
            print(f"Top Entities: {', '.join(s['top_entities'])}")

            # Sample papers (first 3)
            print(f"\nSample Papers:")
            for i, doi in enumerate(s['dois'][:3], 1):
                title = get_title(papers, doi)
                year = next((p.get('year', '?') for p in papers if p['doi'] == doi), '?')
                print(f"  {i}. \"{title[:70]}\" ({year})")

            # DOI list
            doi_limit = len(s['dois']) if full else min(10, len(s['dois']))
            suffix = "" if full or len(s['dois']) <= 10 else f" (use --full for all {len(s['dois'])})"
            print(f"\nDOIs:{suffix}")
            for doi in s['dois'][:doi_limit]:
                print(f"  - {doi}")
            if not full and len(s['dois']) > 10:
                print(f"  ... ({len(s['dois']) - 10} more)")
            print()


def _browse_export(summaries, cluster_ids, papers, output_path):
    """Export selected clusters to JSON."""
    summary_map = {s['cluster_id']: s for s in summaries}
    selected_dois = set()
    for cid in cluster_ids:
        if cid in summary_map:
            selected_dois.update(summary_map[cid]['dois'])

    selected_papers = [p for p in papers if p['doi'] in selected_dois]

    with open(output_path, 'w') as f:
        json.dump(selected_papers, f, indent=2)

    print(f"Selected {len(cluster_ids)} clusters ({len(selected_papers)} papers total)")
    print(f"Exported to: {output_path}")


def run_landscape(args):
    """Generate landscape visualization as HTML."""
    from papersift.embedding import embed_papers
    from papersift import EntityLayerBuilder

    papers = load_papers(args.input)
    use_topics = getattr(args, 'use_topics', False)
    print(f"Loaded {len(papers)} papers", file=sys.stderr)

    # Cluster for coloring
    builder = EntityLayerBuilder(use_topics=use_topics)
    builder.build_from_papers(papers)
    clusters = builder.run_leiden(resolution=args.resolution, seed=args.seed)
    num_clusters = len(set(clusters.values()))
    print(f"Found {num_clusters} clusters", file=sys.stderr)

    # Compute embedding
    print(f"Computing {args.method.upper()} embedding...", file=sys.stderr)

    # Auto-adjust perplexity for t-SNE with small sample sizes
    kwargs = {}
    if args.method == "tsne":
        max_perplexity = (len(papers) - 1) / 3.0
        if max_perplexity < 30.0:
            kwargs['perplexity'] = max(5.0, max_perplexity)
            print(f"  (Adjusted perplexity to {kwargs['perplexity']:.1f} for small sample size)", file=sys.stderr)

    try:
        embedding = embed_papers(papers, method=args.method, use_topics=use_topics, random_state=args.seed, **kwargs)
    except ImportError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("Falling back to t-SNE...", file=sys.stderr)
        embedding = embed_papers(papers, method="tsne", use_topics=use_topics, random_state=args.seed, **kwargs)

    # Build Plotly figure
    try:
        import plotly.graph_objects as go
    except ImportError:
        print("Error: plotly is required for landscape visualization.", file=sys.stderr)
        print("Install with: pip install plotly", file=sys.stderr)
        sys.exit(1)

    # Colorblind-friendly palette
    palette = [
        '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
        '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
        '#aec7e8', '#ffbb78', '#98df8a', '#ff9896', '#c5b0d5',
    ]

    # Get entity info for hover
    paper_entities = builder.paper_entities

    # Group by cluster for legend toggling
    cluster_papers = {}
    for doi, cid in clusters.items():
        cluster_papers.setdefault(cid, []).append(doi)

    fig = go.Figure()
    for i, cid in enumerate(sorted(cluster_papers.keys(), key=str)):
        dois_in_cluster = cluster_papers[cid]
        xs = [embedding[d][0] for d in dois_in_cluster if d in embedding]
        ys = [embedding[d][1] for d in dois_in_cluster if d in embedding]
        titles = [get_title(papers, d) for d in dois_in_cluster]
        entities_hover = [
            ', '.join(list(paper_entities.get(d, set()))[:3])
            for d in dois_in_cluster
        ]
        hover_text = [
            f"<b>{t[:60]}</b><br>Cluster: {cid}<br>Entities: {e}"
            for t, e in zip(titles, entities_hover)
        ]

        fig.add_trace(go.Scatter(
            x=xs, y=ys,
            mode='markers',
            marker=dict(size=8, color=palette[i % len(palette)]),
            name=f'Cluster {cid} ({len(dois_in_cluster)})',
            text=hover_text,
            hoverinfo='text',
        ))

    method_label = args.method.upper()
    fig.update_layout(
        title=f"PaperSift Landscape ({method_label}, {len(papers)} papers)",
        xaxis=dict(showticklabels=False, title=''),
        yaxis=dict(showticklabels=False, title=''),
        hovermode='closest',
        template='plotly_white',
    )

    # Export
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(output_path), include_plotlyjs=True)
    print(f"Saved: {output_path}", file=sys.stderr)

    if getattr(args, 'interactive', False):
        import webbrowser
        webbrowser.open(str(output_path.resolve()))


def run_filter(args):
    """Filter papers by entity, cluster, or DOI list."""
    from papersift import EntityLayerBuilder

    papers = load_papers(args.input)
    matching_dois = set(p['doi'] for p in papers)  # Start with all

    # Entity filter
    if args.entity:
        use_topics = getattr(args, 'use_topics', False)
        builder = EntityLayerBuilder(use_topics=use_topics)
        builder.build_from_papers(papers)

        entity_matches = []
        for entity_name in args.entity:
            found = set(builder.find_papers_by_entity(entity_name))
            entity_matches.append(found)

        if getattr(args, 'entity_any', False):
            # OR: union
            entity_set = set()
            for s in entity_matches:
                entity_set.update(s)
        else:
            # AND: intersection
            entity_set = entity_matches[0]
            for s in entity_matches[1:]:
                entity_set &= s

        matching_dois &= entity_set

    # Cluster filter
    if args.cluster:
        cluster_ids_str = [x.strip() for x in args.cluster.split(',')]

        if args.clusters_from:
            # Load pre-computed clusters
            with open(args.clusters_from) as f:
                clusters = json.load(f)
        else:
            # Cluster on-the-fly
            print("Clustering on-the-fly with resolution=" + str(args.resolution), file=sys.stderr)
            use_topics = getattr(args, 'use_topics', False)
            builder = EntityLayerBuilder(use_topics=use_topics)
            builder.build_from_papers(papers)
            clusters = builder.run_leiden(resolution=args.resolution, seed=42)

        # Match cluster IDs (handle int/str comparison)
        cluster_dois = set()
        for doi, cid in clusters.items():
            if str(cid) in cluster_ids_str:
                cluster_dois.add(doi)

        matching_dois &= cluster_dois

    # DOI list filter
    if args.dois:
        dois_path = args.dois
        with open(dois_path) as f:
            content = f.read().strip()
        try:
            doi_list = json.loads(content)
            if isinstance(doi_list, list):
                doi_set = set(doi_list)
            else:
                doi_set = set(content.splitlines())
        except json.JSONDecodeError:
            doi_set = set(line.strip() for line in content.splitlines() if line.strip())
        matching_dois &= doi_set

    # Apply exclude (invert)
    if getattr(args, 'exclude', False):
        all_dois = set(p['doi'] for p in papers)
        matching_dois = all_dois - matching_dois

    # Filter papers
    filtered = [p for p in papers if p['doi'] in matching_dois]

    # Output
    if args.format == "json":
        output_data = json.dumps(filtered, indent=2)
    else:
        output_data = f"Filtered: {len(filtered)} papers (from {len(papers)} total)\n"
        for p in filtered[:20]:
            output_data += f"  - {p.get('title', p['doi'])[:60]}...\n"
        if len(filtered) > 20:
            output_data += f"  ... and {len(filtered) - 20} more\n"

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, 'w') as f:
            f.write(output_data)
        print(f"Saved {len(filtered)} papers to {out_path}", file=sys.stderr)
    else:
        print(output_data)


def run_merge(args):
    """Merge multiple paper JSON files, deduplicate by DOI."""
    all_papers = []
    seen_dois = set()

    for input_path in args.inputs:
        papers = load_papers(input_path)
        for p in papers:
            if p['doi'] not in seen_dois:
                all_papers.append(p)
                seen_dois.add(p['doi'])

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(all_papers, f, indent=2)

    total_input = sum(len(load_papers(p)) for p in args.inputs)
    deduped = total_input - len(all_papers)
    print(f"Merged {len(args.inputs)} files: {total_input} papers -> {len(all_papers)} unique", file=sys.stderr)
    if deduped > 0:
        print(f"  Removed {deduped} duplicates", file=sys.stderr)
    print(f"Saved: {output_path}", file=sys.stderr)


def run_dedupe(args):
    """Remove non-paper DOIs and deduplicate preprint/published pairs."""
    from papersift.doi import clean_papers, classify_doi, DoiType

    papers = load_papers(args.input)

    cleaned, stats = clean_papers(
        papers,
        remove_non_papers=not getattr(args, 'keep_non_papers', False),
        dedupe_preprints=not getattr(args, 'no_preprint_dedupe', False),
    )

    # Save output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(cleaned, f, indent=2)

    # Print summary
    print(f"Input: {stats['total_input']} papers", file=sys.stderr)
    print(f"Output: {stats['final_count']} papers", file=sys.stderr)
    removed = stats['total_input'] - stats['final_count']
    if removed > 0:
        print(f"Removed: {removed} entries", file=sys.stderr)
        if stats.get('removed_datasets', 0):
            print(f"  - Datasets (zenodo/figshare/etc): {stats['removed_datasets']}", file=sys.stderr)
        if stats.get('removed_supplementary', 0):
            print(f"  - Supplementary files: {stats['removed_supplementary']}", file=sys.stderr)
        if stats.get('removed_editorial', 0):
            print(f"  - Editorial/recommendations: {stats['removed_editorial']}", file=sys.stderr)
        if stats.get('removed_preprint_duplicates', 0):
            print(f"  - Preprint duplicates: {stats['removed_preprint_duplicates']}", file=sys.stderr)
        if stats.get('removed_other', 0):
            print(f"  - Other non-papers: {stats['removed_other']}", file=sys.stderr)

    if getattr(args, 'report', False):
        # Detailed report
        print(f"\nDOI Type Distribution (input):", file=sys.stderr)
        for dtype, count in sorted(stats.get('doi_types', {}).items()):
            print(f"  {dtype}: {count}", file=sys.stderr)

    print(f"\nSaved: {output_path}", file=sys.stderr)


def run_abstract(args):
    """Execute abstract fetch command."""
    from papersift.abstract import AbstractFetcher, attach_abstracts

    papers = load_papers(args.input)
    print(f"Loaded {len(papers)} papers", file=sys.stderr)

    fetcher = AbstractFetcher(
        email=args.email,
        skip_epmc=getattr(args, 'skip_epmc', False),
    )
    abstracts = fetcher.fetch_all(papers)
    papers, stats = attach_abstracts(papers, abstracts)

    # Save output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(papers, f, indent=2, ensure_ascii=False)

    # Print summary
    total = stats['total']
    with_abs = stats['with_abstract']
    print(f"\n=== Summary ===", file=sys.stderr)
    print(f"Total papers: {total}", file=sys.stderr)
    print(f"With abstract: {with_abs} ({100*with_abs/total:.1f}%)" if total else "With abstract: 0", file=sys.stderr)
    print(f"Without abstract: {stats['without_abstract']}", file=sys.stderr)
    if stats['without_doi']:
        print(f"Without DOI: {stats['without_doi']}", file=sys.stderr)
    print(f"\nSaved: {output_path}", file=sys.stderr)


def _run_claude_extraction(prompts, max_parallel=5):
    """Run LLM extraction via claude CLI subprocess in parallel batches.

    Args:
        prompts: List of extraction prompt strings
        max_parallel: Max concurrent subprocess calls

    Returns:
        List of lists of extraction dicts (one list per prompt batch)
    """
    import concurrent.futures
    import shutil
    import subprocess

    from papersift.extract import parse_llm_response

    results = [None] * len(prompts)

    def extract_one(idx, prompt):
        try:
            result = subprocess.run(
                ['claude', '-p', '--output-format', 'json'],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode != 0:
                print(f"  Warning: Batch {idx+1} claude CLI returned code {result.returncode}", file=sys.stderr)
                return idx, []
            response = json.loads(result.stdout)
            text = response.get('result', '')
            return idx, parse_llm_response(text)
        except subprocess.TimeoutExpired:
            print(f"  Warning: Batch {idx+1} timed out after 300s", file=sys.stderr)
            return idx, []
        except (json.JSONDecodeError, KeyError) as e:
            print(f"  Warning: Batch {idx+1} parse error: {e}", file=sys.stderr)
            return idx, []

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_parallel) as pool:
        futures = {pool.submit(extract_one, i, p): i for i, p in enumerate(prompts)}
        for future in concurrent.futures.as_completed(futures):
            idx, parsed = future.result()
            results[idx] = parsed
            print(f"  Batch {idx+1}/{len(prompts)}: {len(parsed)} extractions", file=sys.stderr)

    # Replace any None entries (shouldn't happen, but safety)
    return [r if r is not None else [] for r in results]


def run_research(args):
    """Execute research pipeline command."""
    from papersift.research import ResearchPipeline

    papers = load_papers(args.input)
    print(f"Loaded {len(papers)} papers", file=sys.stderr)

    pipeline = ResearchPipeline(
        use_topics=getattr(args, 'use_topics', False),
        resolution=args.resolution,
        seed=args.seed,
    )

    # Always run Phase 1
    clusters_from = Path(args.clusters_from) if args.clusters_from else None
    prepared = pipeline.prepare(
        papers,
        email=args.email,
        skip_epmc=getattr(args, 'skip_epmc', False),
        clusters_from=clusters_from,
    )

    output_dir = Path(args.output)

    # Phase 2 if extractions provided
    if args.extractions_from:
        output = pipeline.finalize(
            prepared,
            extractions_from=Path(args.extractions_from),
        )
        pipeline.export(output, output_dir, prepared=prepared)
        print(f"\nPipeline complete. Output in {output_dir}/", file=sys.stderr)
    else:
        import shutil

        # Always save prompts for reproducibility
        output_dir.mkdir(parents=True, exist_ok=True)
        from papersift.extract import save_prompts
        prompts_path = output_dir / "extraction_prompts.json"
        save_prompts(prepared.prompts, prepared.batch_doi_lists, prompts_path)

        n_prompts = len(prepared.prompts)
        no_llm = getattr(args, 'no_llm', False)

        # Auto-extract if claude CLI is available and not skipped
        if shutil.which('claude') and not no_llm:
            print(f"\nRunning LLM extraction via claude CLI ({n_prompts} batches)...", file=sys.stderr)
            llm_results = _run_claude_extraction(prepared.prompts, max_parallel=5)

            output = pipeline.finalize(prepared, llm_results=llm_results)
            pipeline.export(output, output_dir, prepared=prepared)
            print(f"\nPipeline complete. Output in {output_dir}/", file=sys.stderr)
        else:
            # Fallback: Phase 1 only
            output = pipeline.finalize(prepared)
            pipeline.export(output, output_dir, prepared=prepared)

            print(f"\nPhase 1 complete. {n_prompts} extraction prompts saved to {prompts_path}", file=sys.stderr)
            print(f"\nTo complete the pipeline:", file=sys.stderr)
            print(f"  1. Run LLM extraction on the prompts (e.g., via Claude Code Task tool)", file=sys.stderr)
            print(f"  2. Save results to a JSON file", file=sys.stderr)
            print(f"  3. Run: papersift research {args.input} -o {args.output} --extractions-from <results.json>", file=sys.stderr)


def run_subcluster(args):
    """Sub-cluster a specific cluster using the standalone sub_cluster function."""
    from papersift.embedding import sub_cluster

    papers = load_papers(args.input)

    with open(args.clusters_from) as f:
        clusters = json.load(f)

    use_topics = getattr(args, 'use_topics', False)
    target_cid = args.cluster

    # Try to match as int if possible (clusters.json values are often ints)
    try:
        target_cid_int = int(target_cid)
        if any(v == target_cid_int for v in clusters.values()):
            target_cid = target_cid_int
    except ValueError:
        pass

    try:
        sub_results = sub_cluster(
            papers, target_cid, clusters,
            resolution=args.resolution,
            seed=args.seed,
            use_topics=use_topics,
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Count sub-clusters
    from collections import Counter
    sub_counts = Counter(sub_results.values())

    if args.format == "json":
        output = json.dumps(sub_results, indent=2)
        if args.output:
            output_dir = Path(args.output)
            output_dir.mkdir(parents=True, exist_ok=True)
            # Save updated clusters (merge sub_results into original)
            updated_clusters = dict(clusters)
            updated_clusters.update(sub_results)
            with open(output_dir / "clusters.json", 'w') as f:
                json.dump(updated_clusters, f, indent=2)
            print(f"Saved updated clusters to {output_dir / 'clusters.json'}", file=sys.stderr)
        else:
            print(output)
    else:
        print(f"\nSub-clusters of cluster {args.cluster}:")
        print(f"  {len(sub_results)} papers -> {len(sub_counts)} sub-clusters\n")
        for scid, count in sub_counts.most_common():
            print(f"  Sub-cluster {scid}: {count} papers")

        if args.output:
            output_dir = Path(args.output)
            output_dir.mkdir(parents=True, exist_ok=True)
            updated_clusters = dict(clusters)
            updated_clusters.update(sub_results)
            with open(output_dir / "clusters.json", 'w') as f:
                json.dump(updated_clusters, f, indent=2)
            print(f"\nSaved: {output_dir / 'clusters.json'}")


def _require_pipeline():
    """Import pipeline modules or exit with helpful error."""
    try:
        from papersift.pipeline import PaperDiscovery, PaperFetcher, PaperExtractor, PaperStore
        return PaperDiscovery, PaperFetcher, PaperExtractor, PaperStore
    except ImportError:
        print("Error: Pipeline commands require additional dependencies.", file=sys.stderr)
        print("Install with: pip install papersift[pipeline]", file=sys.stderr)
        sys.exit(1)


def run_search(args):
    """Execute search command."""
    PaperDiscovery, _, _, PaperStore = _require_pipeline()

    email = args.email or os.environ.get("PAPER_PIPELINE_EMAIL")
    if not email:
        print("Error: Email required. Use --email or set PAPER_PIPELINE_EMAIL", file=sys.stderr)
        sys.exit(1)

    discovery = PaperDiscovery(email=email)

    filters = {}
    if args.oa_only:
        filters["is_oa"] = True
    if args.year_min:
        filters["publication_year"] = f">{args.year_min - 1}"

    print(f"Searching for: {args.query}")
    papers = discovery.search(
        query=args.query,
        max_results=args.max,
        filters=filters if filters else None,
    )
    print(f"Found {len(papers)} papers")

    # Save to store
    store = PaperStore(args.data_dir)
    saved = 0
    for paper in papers:
        if paper.get("doi"):
            store.save_layer(paper["doi"], "L0", paper)
            saved += 1
    print(f"Saved {saved} papers to {args.data_dir}")

    if args.collection:
        dois = [p["doi"] for p in papers if p.get("doi")]
        store.add_to_collection(args.collection, dois)
        print(f"Added to collection: {args.collection}")

    # Export flat JSON for clustering if requested
    if args.output:
        import json as _json
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            _json.dump(papers, f, indent=2, ensure_ascii=False)
        print(f"Exported {len(papers)} papers to {args.output}")

    if papers and not getattr(args, 'quiet', False):
        print("\nTop papers:")
        for i, p in enumerate(papers[:5], 1):
            print(f"  {i}. {p.get('title', 'Unknown')[:60]}...")
            print(f"     DOI: {p.get('doi', 'N/A')} | Year: {p.get('publication_year', 'N/A')} | Cited: {p.get('cited_by_count', 0)}")


def run_fetch(args):
    """Execute fetch command."""
    _, PaperFetcher, PaperExtractor, PaperStore = _require_pipeline()

    email = args.email or os.environ.get("PAPER_PIPELINE_EMAIL")
    if not email:
        print("Error: Email required. Use --email or set PAPER_PIPELINE_EMAIL", file=sys.stderr)
        sys.exit(1)

    store = PaperStore(args.data_dir)
    fetcher = PaperFetcher(email=email)
    extractor = PaperExtractor(grobid_url=args.grobid_url)

    dois = []
    if args.doi:
        dois = [args.doi]
    elif args.collection:
        dois = store.get_collection(args.collection)
        if not dois:
            print(f"Collection not found: {args.collection}", file=sys.stderr)
            sys.exit(1)
    else:
        papers = store.list_papers(filters={"has_layer": "L0"})
        dois = [p["doi"] for p in papers if not p.get("content_available")]

    print(f"Fetching content for {len(dois)} papers...")

    success = 0
    for doi in dois:
        metadata = store.load_layer(doi, "L0")
        if not metadata:
            print(f"  [SKIP] {doi} - No L0 metadata")
            continue

        content_dir = store.get_paper_dir(doi) / "content"
        result = fetcher.fetch_content(doi=doi, work_data=metadata, save_dir=content_dir)

        if result.content_type in ("pmc_xml", "pdf"):
            extraction = extractor.extract(
                content_type=result.content_type,
                data=result.data,
                pdf_path=result.pdf_path,
            )
            if result.content_type == "pmc_xml" and result.data:
                store.save_content(doi, "europe_pmc_xml", result.data)
            if extraction.full_text:
                store.save_content(doi, "fulltext", extraction.full_text)
            store.update_paper_metadata(doi=doi, content_source=result.source, extraction_method=extraction.extraction_method)
            if extraction.sections:
                store.save_layer(doi, "L2", {"sections": extraction.sections, "abstract": extraction.abstract, "extraction_method": extraction.extraction_method})
            print(f"  [OK] {doi} - {result.source}/{extraction.extraction_method}")
            success += 1
        else:
            print(f"  [SKIP] {doi} - {result.content_type}")

    print(f"\nFetched {success}/{len(dois)} papers")


def run_status(args):
    """Execute status command."""
    _, _, _, PaperStore = _require_pipeline()
    store = PaperStore(args.data_dir)
    stats = store.get_stats()

    print(f"Paper Store Status ({args.data_dir})")
    print("=" * 50)
    print(f"Total papers: {stats['total_papers']}")
    print(f"Collections: {stats['collections']}")
    print(f"\nLayers:")
    for layer, count in stats["by_layer"].items():
        print(f"  {layer}: {count}")
    print(f"\nContent available: {stats['content_available']}")
    if stats["by_extraction_method"]:
        print("\nExtraction methods:")
        for method, count in stats["by_extraction_method"].items():
            print(f"  {method}: {count}")


def run_collection(args):
    """Execute collection command."""
    _, _, _, PaperStore = _require_pipeline()
    store = PaperStore(args.data_dir)

    if not args.collection_cmd:
        print("Usage: papersift collection {list|show|create|export}", file=sys.stderr)
        sys.exit(1)

    if args.collection_cmd == "list":
        collections = store.list_collections()
        if not collections:
            print("No collections found")
        else:
            print("Collections:")
            for name in collections:
                dois = store.get_collection(name) or []
                print(f"  {name}: {len(dois)} papers")

    elif args.collection_cmd == "show":
        dois = store.get_collection(args.name)
        if not dois:
            print(f"Collection not found: {args.name}", file=sys.stderr)
            sys.exit(1)
        print(f"Collection: {args.name} ({len(dois)} papers)\n")
        for doi in dois:
            metadata = store.load_layer(doi, "L0")
            if metadata:
                print(f"  - {doi}")
                print(f"    {metadata.get('title', 'Unknown')[:60]}... ({metadata.get('publication_year', 'N/A')})")
            else:
                print(f"  - {doi} (no metadata)")

    elif args.collection_cmd == "create":
        dois = [d.strip() for d in args.dois.split(",") if d.strip()]
        store.create_collection(args.name, dois)
        print(f"Created collection '{args.name}' with {len(dois)} papers")

    elif args.collection_cmd == "export":
        papers = store.export_papers_json(collection=args.name)
        if not papers:
            print(f"Collection not found or empty: {args.name}", file=sys.stderr)
            sys.exit(1)
        import json as _json
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            _json.dump(papers, f, indent=2, ensure_ascii=False)
        print(f"Exported {len(papers)} papers to {args.output}")


if __name__ == "__main__":
    main()
