#!/usr/bin/env python3
"""PaperSift CLI: Entity-based paper clustering and exploration."""

import argparse
import json
import sys
from pathlib import Path


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

  # Stream from seed paper
  papersift stream papers.json --seed "https://doi.org/10.1101/..." --hops 5
        """
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

    args = parser.parse_args()

    if args.command == "cluster":
        run_cluster(args)
    elif args.command == "find":
        run_find(args)
    elif args.command == "stream":
        run_stream(args)


def run_find(args):
    """Execute find command."""
    from papersift import EntityLayerBuilder

    papers = load_papers(args.input)
    use_topics = getattr(args, 'use_topics', False)
    builder = EntityLayerBuilder(use_topics=use_topics)
    builder.build_from_papers(papers)

    if args.hubs:
        hubs = builder.find_hub_papers(top_k=args.hubs)
        print(f"Top {args.hubs} Entity Hub Papers:")
        print("-" * 60)
        for i, h in enumerate(hubs, 1):
            title = get_title(papers, h['doi'])
            print(f"{i:2d}. [{h['hub_score']:4d}] {title[:50]}...")
            print(f"    Entities: {', '.join(h['entities'][:5])}")

    elif args.entity:
        dois = builder.find_papers_by_entity(args.entity)
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
        print(f"Papers reachable in {args.hops} hops from seed: {len(reachable)}")
        for doi in list(reachable)[:20]:
            title = get_title(papers, doi)
            print(f"  - {title[:60]}...")
    else:
        path = builder.entity_stream(args.seed, strategy=args.strategy, max_hops=args.hops)
        print(f"Entity stream ({args.strategy}, {len(path)} papers):")
        for i, doi in enumerate(path):
            title = get_title(papers, doi)
            marker = ">" if i == 0 else " "
            print(f"{marker} {i}. {title[:55]}...")


def load_papers(path):
    with open(path) as f:
        data = json.load(f)
    return data.get('papers', data)


def get_title(papers, doi):
    return next((p['title'] for p in papers if p['doi'] == doi), doi)


def run_cluster(args):
    """Execute clustering command."""
    from papersift import EntityLayerBuilder, ClusterValidator

    # Load papers
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: File not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    with open(input_path) as f:
        data = json.load(f)

    papers = data.get('papers', data)  # Support both {papers: [...]} and [...]
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


if __name__ == "__main__":
    main()
