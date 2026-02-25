"""Research pipeline orchestrator for PaperSift.

This module orchestrates the full research workflow:
1. prepare(): Cluster papers, fetch abstracts, build LLM extraction prompts
2. finalize(): Merge LLM results, build enriched output, export

The prepare/finalize pattern enables parallel LLM extraction by Claude Code agents.
"""

import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from papersift.abstract import AbstractFetcher, attach_abstracts
from papersift.entity_layer import EntityLayerBuilder
from papersift.extract import (
    build_batch_prompts,
    load_extractions,
    merge_extractions,
    save_prompts,
)


@dataclass
class PreparedData:
    """Output from prepare() phase - ready for LLM extraction."""

    papers: list[dict]  # papers with abstracts attached
    clusters: dict[str, int]  # doi -> cluster_id mapping
    cluster_summaries: list[dict]  # per-cluster summary with top entities
    paper_entities: dict[str, list[str]]  # per-paper entity lists keyed by DOI
    prompts: list[str]  # extraction prompts for LLM subagents
    batch_doi_lists: list[list[str]]  # DOI tracking per prompt batch
    stats: dict  # abstract coverage stats
    metadata: dict = field(default_factory=dict)  # pipeline params


@dataclass
class ResearchOutput:
    """Output from finalize() phase - enriched papers ready for analysis."""

    papers: list[dict]  # fully enriched paper records
    clusters: dict[str, int]  # doi -> cluster_id
    cluster_summaries: list[dict]  # per-cluster summary with top entities
    stats: dict  # pipeline statistics
    metadata: dict = field(default_factory=dict)  # pipeline metadata


class ResearchPipeline:
    """Research pipeline orchestrator with prepare/finalize pattern."""

    def __init__(self, use_topics: bool = False, resolution: float = 1.0, seed: int = 42):
        """Initialize the research pipeline.

        Args:
            use_topics: If True, use OpenAlex topics as entities in addition to title extraction
            resolution: Leiden clustering resolution (higher = more clusters)
            seed: Random seed for reproducible clustering
        """
        self.use_topics = use_topics
        self.resolution = resolution
        self.seed = seed

    def prepare(
        self,
        papers: list[dict],
        email: str = "",
        skip_epmc: bool = False,
        clusters_from: Path | None = None,
    ) -> PreparedData:
        """Phase 1: Cluster + fetch abstracts + build extraction prompts.

        Args:
            papers: List of paper dicts with doi, title, year fields
            email: Email for OpenAlex polite pool (recommended for faster access)
            skip_epmc: Skip Europe PMC individual queries (faster but lower coverage)
            clusters_from: Path to JSON file with {doi: cluster_id} mapping (optional)

        Returns:
            PreparedData with everything needed for LLM extraction
        """
        print(f"\n=== Phase 1: Prepare ({len(papers)} papers) ===\n", file=sys.stderr)

        # Step 1: Cluster papers
        print("Step 1: Clustering papers...", file=sys.stderr)
        builder = EntityLayerBuilder(use_topics=self.use_topics)
        builder.build_from_papers(papers)

        if clusters_from:
            print(f"  Loading clusters from {clusters_from}", file=sys.stderr)
            with open(clusters_from, "r", encoding="utf-8") as f:
                clusters = json.load(f)
            # Convert cluster IDs to int if they were saved as strings
            clusters = {doi: int(cid) for doi, cid in clusters.items()}
        else:
            print(
                f"  Running Leiden (resolution={self.resolution}, seed={self.seed})",
                file=sys.stderr,
            )
            clusters = builder.run_leiden(resolution=self.resolution, seed=self.seed)

        summaries = builder.get_cluster_summary(clusters)
        paper_entities = {
            doi: sorted(list(ents)) for doi, ents in builder.paper_entities.items()
        }

        print(f"  Created {len(summaries)} clusters", file=sys.stderr)
        for summary in summaries[:5]:
            print(
                f"    Cluster {summary['cluster_id']}: {summary['size']} papers - {', '.join(summary['top_entities'][:3])}",
                file=sys.stderr,
            )

        # Step 2: Fetch abstracts
        print("\nStep 2: Fetching abstracts...", file=sys.stderr)
        fetcher = AbstractFetcher(email=email, skip_epmc=skip_epmc)
        abstracts = fetcher.fetch_all(papers)
        papers, stats = attach_abstracts(papers, abstracts)

        print(
            f"  Abstract coverage: {stats['with_abstract']}/{stats['total']} ({100*stats['with_abstract']/stats['total']:.1f}%)",
            file=sys.stderr,
        )

        # Step 3: Build extraction prompts
        print("\nStep 3: Building extraction prompts...", file=sys.stderr)
        prompts, batch_doi_lists = build_batch_prompts(papers)
        print(f"  Created {len(prompts)} prompts for {len(papers)} papers", file=sys.stderr)

        metadata = {
            "timestamp": datetime.now().isoformat(),
            "resolution": self.resolution,
            "seed": self.seed,
            "use_topics": self.use_topics,
            "version": "1.0",
        }

        return PreparedData(
            papers=papers,
            clusters=clusters,
            cluster_summaries=summaries,
            paper_entities=paper_entities,
            prompts=prompts,
            batch_doi_lists=batch_doi_lists,
            stats=stats,
            metadata=metadata,
        )

    def finalize(
        self,
        prepared: PreparedData,
        llm_results: list[list[dict]] | None = None,
        extractions_from: Path | None = None,
    ) -> ResearchOutput:
        """Phase 2: Merge LLM results + build enriched output.

        Args:
            prepared: PreparedData from prepare() phase
            llm_results: List of lists of extraction dicts (programmatic, from Claude Code)
            extractions_from: Path to JSON file with pre-computed extractions (CLI)

        Returns:
            ResearchOutput with fully enriched papers
        """
        print(f"\n=== Phase 2: Finalize ===\n", file=sys.stderr)

        # Load extractions
        extractions = []
        if llm_results is not None:
            print("Loading extractions from llm_results...", file=sys.stderr)
            # Flatten list of lists
            for batch in llm_results:
                extractions.extend(batch)
            print(f"  Loaded {len(extractions)} extractions", file=sys.stderr)
        elif extractions_from is not None:
            print(f"Loading extractions from {extractions_from}...", file=sys.stderr)
            extractions = load_extractions(extractions_from)
            print(f"  Loaded {len(extractions)} extractions", file=sys.stderr)
        else:
            print("No extractions provided - skipping merge", file=sys.stderr)

        # Merge extractions into papers
        if extractions:
            merge_extractions(prepared.papers, extractions)

        # Build enriched output schema
        print("\nBuilding enriched output...", file=sys.stderr)
        enriched_papers = []

        # Build cluster label lookup
        cluster_labels = {}
        for summary in prepared.cluster_summaries:
            cid = summary["cluster_id"]
            label = ", ".join(summary["top_entities"][:5])
            cluster_labels[cid] = label

        for paper in prepared.papers:
            doi = paper.get("doi", "")
            cluster_id = prepared.clusters.get(doi)

            enriched = {
                "doi": doi,
                "title": paper.get("title", ""),
                "year": paper.get("year"),
                "cluster_id": str(cluster_id) if cluster_id is not None else None,
                "cluster_label": cluster_labels.get(cluster_id, ""),
                "abstract": paper.get("abstract", ""),
                "problem": paper.get("problem", ""),
                "method": paper.get("method", ""),
                "finding": paper.get("finding", ""),
                "entities": prepared.paper_entities.get(doi, []),
            }
            enriched_papers.append(enriched)

        # Calculate stats
        total = len(enriched_papers)
        with_abstract = sum(1 for p in enriched_papers if p["abstract"])
        with_extraction = sum(
            1
            for p in enriched_papers
            if p["problem"] or p["method"] or p["finding"]
        )

        stats = {
            "paper_count": total,
            "cluster_count": len(prepared.cluster_summaries),
            "abstract_coverage": round(100 * with_abstract / total, 1) if total else 0,
            "extraction_coverage": (
                round(100 * with_extraction / total, 1) if total else 0
            ),
        }

        print(
            f"  Papers: {total}, Clusters: {stats['cluster_count']}, Abstract coverage: {stats['abstract_coverage']}%, Extraction coverage: {stats['extraction_coverage']}%",
            file=sys.stderr,
        )

        return ResearchOutput(
            papers=enriched_papers,
            clusters=prepared.clusters,
            cluster_summaries=prepared.cluster_summaries,
            stats=stats,
            metadata=prepared.metadata,
        )

    def export(
        self,
        output: ResearchOutput,
        output_dir: Path,
        prepared: PreparedData | None = None,
    ) -> None:
        """Export results to files.

        Args:
            output: ResearchOutput from finalize()
            output_dir: Directory to write output files
            prepared: Optional PreparedData (for exporting prompts)
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        # 1. enriched_papers.json
        enriched_path = output_dir / "enriched_papers.json"
        print(f"\nExporting enriched_papers.json to {enriched_path}...", file=sys.stderr)
        with open(enriched_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "papers": output.papers,
                    "clusters": output.clusters,
                    "cluster_summaries": output.cluster_summaries,
                    "stats": output.stats,
                    "metadata": output.metadata,
                },
                f,
                indent=2,
                ensure_ascii=False,
            )

        # 2. clusters.json (standalone, for papersift filter compatibility)
        clusters_path = output_dir / "clusters.json"
        print(f"Exporting clusters.json to {clusters_path}...", file=sys.stderr)
        with open(clusters_path, "w", encoding="utf-8") as f:
            json.dump(output.clusters, f, indent=2, ensure_ascii=False)

        # 3. for_research.md
        research_md_path = output_dir / "for_research.md"
        print(f"Exporting for_research.md to {research_md_path}...", file=sys.stderr)
        self._export_research_briefing(output, research_md_path)

        # 4. extraction_prompts.json (if prepared data available)
        if prepared and prepared.prompts:
            prompts_path = output_dir / "extraction_prompts.json"
            print(f"Exporting extraction_prompts.json to {prompts_path}...", file=sys.stderr)
            save_prompts(prepared.prompts, prepared.batch_doi_lists, prompts_path)

        print(f"\nExport complete to {output_dir}", file=sys.stderr)

    def _export_research_briefing(
        self, output: ResearchOutput, output_path: Path
    ) -> None:
        """Generate for_research.md briefing for omc:research integration.

        Each cluster section is SELF-CONTAINED with full paper details.
        """
        # Group papers by cluster
        cluster_papers = defaultdict(list)
        for paper in output.papers:
            cid = paper.get("cluster_id")
            if cid is not None:
                cluster_papers[cid].append(paper)

        # Build markdown
        lines = []
        lines.append("# Research Briefing\n")

        # Dataset overview
        stats = output.stats
        meta = output.metadata
        lines.append("## Dataset Overview\n")
        lines.append(
            f"- {stats['paper_count']} papers, {stats['cluster_count']} clusters, "
            f"{stats['abstract_coverage']}% abstract coverage, "
            f"{stats['extraction_coverage']}% extraction coverage"
        )
        lines.append(
            f"- Parameters: resolution={meta.get('resolution')}, "
            f"use_topics={meta.get('use_topics')}, seed={meta.get('seed')}"
        )
        lines.append("")

        # Per-cluster sections
        for summary in output.cluster_summaries:
            cid = str(summary["cluster_id"])
            label = ", ".join(summary["top_entities"][:5])
            size = summary["size"]

            papers = cluster_papers.get(cid, [])

            lines.append(f"## Cluster {cid}: {label} ({size} papers)\n")

            # Summary
            lines.append("### Summary\n")

            # Common problems
            problems = [p["problem"] for p in papers if p.get("problem")]
            if problems:
                problem_counts = Counter(problems)
                top_problems = problem_counts.most_common(5)
                lines.append("**Common problems**:")
                for prob, count in top_problems:
                    lines.append(f"- {prob} ({count})")
            else:
                lines.append("**Common problems**: No extractions available")
            lines.append("")

            # Dominant methods
            methods = [p["method"] for p in papers if p.get("method")]
            if methods:
                method_counts = Counter(methods)
                top_methods = method_counts.most_common(5)
                lines.append("**Dominant methods**:")
                for meth, count in top_methods:
                    lines.append(f"- {meth} ({count})")
            else:
                lines.append("**Dominant methods**: No extractions available")
            lines.append("")

            # Key findings
            findings = [p["finding"] for p in papers if p.get("finding")]
            if findings:
                # First 3 non-empty findings, truncated to 100 chars
                key_findings = " | ".join(
                    f[:100] + ("..." if len(f) > 100 else "") for f in findings[:3]
                )
                lines.append(f"**Key findings**: {key_findings}")
            else:
                lines.append("**Key findings**: No extractions available")
            lines.append("")

            # Papers table
            lines.append("### Papers\n")
            papers_with_abstract = [p for p in papers if p.get("abstract")]
            papers_without_abstract = [p for p in papers if not p.get("abstract")]

            if papers_with_abstract:
                lines.append("| # | DOI | Title | Year | Method | Finding |")
                lines.append("|---|-----|-------|------|--------|---------|")
                for i, paper in enumerate(papers_with_abstract, 1):
                    doi = paper.get("doi", "")
                    title = paper.get("title", "").replace("|", "\\|")
                    year = paper.get("year", "")
                    method = paper.get("method", "").replace("|", "\\|")[:100]
                    finding = paper.get("finding", "").replace("|", "\\|")[:100]
                    lines.append(f"| {i} | {doi} | {title} | {year} | {method} | {finding} |")
                lines.append("")

            if papers_without_abstract:
                lines.append("### Papers Without Abstracts\n")
                for paper in papers_without_abstract:
                    doi = paper.get("doi", "")
                    title = paper.get("title", "")
                    lines.append(f"- {doi}: {title}")
                lines.append("")

            lines.append("---\n")

        # Cross-cluster patterns
        lines.append("## Cross-Cluster Patterns\n")

        # Shared methods across clusters
        cluster_methods = defaultdict(set)
        for paper in output.papers:
            cid = paper.get("cluster_id")
            method = paper.get("method")
            if cid and method:
                cluster_methods[cid].add(method)

        if cluster_methods:
            # Methods shared by 2+ clusters
            method_to_clusters = defaultdict(set)
            for cid, methods in cluster_methods.items():
                for method in methods:
                    method_to_clusters[method].add(cid)

            shared_methods = {
                m: cs for m, cs in method_to_clusters.items() if len(cs) >= 2
            }
            if shared_methods:
                lines.append("**Methods shared across clusters**:")
                for method, cluster_ids in sorted(
                    shared_methods.items(), key=lambda x: -len(x[1])
                )[:5]:
                    clusters_str = ", ".join(sorted(cluster_ids))
                    lines.append(f"- {method} (clusters: {clusters_str})")
            else:
                lines.append("**Methods shared across clusters**: None")
            lines.append("")

            # Unique methods per cluster (methods in only 1 cluster)
            unique_methods = {
                m: cs for m, cs in method_to_clusters.items() if len(cs) == 1
            }
            if unique_methods:
                cluster_unique_counts = Counter()
                for method, cluster_ids in unique_methods.items():
                    cid = next(iter(cluster_ids))
                    cluster_unique_counts[cid] += 1

                lines.append("**Unique methods per cluster**:")
                for cid, count in cluster_unique_counts.most_common(5):
                    label = next(
                        (
                            ", ".join(s["top_entities"][:3])
                            for s in output.cluster_summaries
                            if str(s["cluster_id"]) == cid
                        ),
                        cid,
                    )
                    lines.append(f"- Cluster {cid} ({label}): {count} unique methods")
            else:
                lines.append("**Unique methods per cluster**: None")
            lines.append("")

        # Clusters with highest abstract coverage
        cluster_abstract_rates = {}
        for summary in output.cluster_summaries:
            cid = str(summary["cluster_id"])
            papers = cluster_papers.get(cid, [])
            if papers:
                with_abstract = sum(1 for p in papers if p.get("abstract"))
                rate = 100 * with_abstract / len(papers)
                cluster_abstract_rates[cid] = rate

        if cluster_abstract_rates:
            lines.append("**Clusters with highest abstract coverage**:")
            for cid, rate in sorted(
                cluster_abstract_rates.items(), key=lambda x: -x[1]
            )[:5]:
                label = next(
                    (
                        ", ".join(s["top_entities"][:3])
                        for s in output.cluster_summaries
                        if str(s["cluster_id"]) == cid
                    ),
                    cid,
                )
                size = len(cluster_papers.get(cid, []))
                lines.append(f"- Cluster {cid} ({label}): {rate:.1f}% ({size} papers)")
            lines.append("")

        # Write to file
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
