#!/usr/bin/env python3
"""
e002 v2: OpenAlex fulltext indexing coverage and SOTA filtering pattern analysis

Changes from v1:
- Fixed: .search() -> fulltext.search filter (fulltext-only, not combined search)
- Fixed: per_page=25 bug -> get(per_page=200) for full coverage
- Improved: seed selection diversified across clusters (median-cited, not top-cited)
"""
import json
import time
from pathlib import Path
from typing import Dict, List, Tuple
from collections import defaultdict

try:
    from pyalex import Works, config
    config.email = "kyuwon.shim@ip-korea.org"
except ImportError:
    print("ERROR: pyalex not installed. Install with: pip install pyalex")
    exit(1)


def load_papers(papers_path: str) -> List[Dict]:
    """Load papers from JSON file."""
    with open(papers_path) as f:
        return json.load(f)


def doi_to_openalex_id(doi: str) -> str:
    """Convert DOI to OpenAlex ID format."""
    # OpenAlex uses doi: prefix
    return f"https://doi.org/{doi}"


def batch_check_fulltext(dois: List[str], batch_size: int = 50) -> Tuple[int, int]:
    """
    Check how many papers have fulltext indexed in OpenAlex.
    Returns: (total_checked, fulltext_available)
    """
    total_checked = 0
    fulltext_count = 0

    for i in range(0, len(dois), batch_size):
        batch = dois[i:i+batch_size]
        doi_filter = "|".join(batch)

        # Query with has_fulltext filter
        try:
            results = Works().filter(doi=doi_filter, has_fulltext=True).get(per_page=200)
            batch_fulltext = len(results)

            # Also check total in this batch to verify
            total_results = Works().filter(doi=doi_filter).get(per_page=200)
            batch_total = len(total_results)

            total_checked += batch_total
            fulltext_count += batch_fulltext

            print(f"Batch {i//batch_size + 1}: {batch_fulltext}/{batch_total} have fulltext "
                  f"({100*batch_fulltext/batch_total:.1f}%)")

            time.sleep(0.15)  # Respect rate limit (10 req/sec)

        except Exception as e:
            print(f"Error in batch {i//batch_size + 1}: {e}")
            continue

    return total_checked, fulltext_count


def test_filter_patterns(seed_papers: List[Dict]) -> Dict:
    """
    Test different text search patterns on citing papers of seed papers.
    Returns: pattern -> [hit_counts per seed]
    """
    patterns = {
        "sota_narrow": "outperforms OR surpasses OR beats",
        "sota_broad": "state-of-the-art OR achieves new best OR sets new record",
        "method_proposal": "we propose OR novel method OR new framework OR new approach",
        "improvement": "improves upon OR extends OR enhances OR advances",
        "combined": "we propose OR novel method OR outperforms OR state-of-the-art OR improves upon",
    }

    results = defaultdict(list)

    for idx, paper in enumerate(seed_papers):
        doi = paper['doi']
        title = paper['title']

        print(f"\nSeed {idx+1}/{len(seed_papers)}: {title[:60]}...")

        # Get OpenAlex ID from DOI
        try:
            work = Works().filter(doi=doi).get()
            if not work:
                print(f"  ERROR: Paper not found in OpenAlex")
                continue

            oa_id = work[0]['id']

            # Get total citing count
            total_citing = Works().filter(cites=oa_id).count()
            print(f"  Total citing papers: {total_citing}")

            if total_citing == 0:
                print(f"  WARNING: No citing papers found")
                for pattern_name in patterns.keys():
                    results[pattern_name].append({
                        'seed_doi': doi,
                        'seed_title': title,
                        'total_citing': 0,
                        'hit_count': 0,
                        'hit_rate': 0.0
                    })
                continue

            # Test each pattern
            for pattern_name, pattern_query in patterns.items():
                try:
                    # Search in fulltext of citing papers (fulltext-only filter)
                    hits = Works().filter(cites=oa_id, fulltext={"search": pattern_query}).count()
                    hit_rate = hits / total_citing if total_citing > 0 else 0.0

                    results[pattern_name].append({
                        'seed_doi': doi,
                        'seed_title': title,
                        'total_citing': total_citing,
                        'hit_count': hits,
                        'hit_rate': hit_rate
                    })

                    print(f"  {pattern_name:20s}: {hits:4d} hits ({100*hit_rate:5.1f}%)")

                    time.sleep(0.12)  # Rate limit

                except Exception as e:
                    print(f"  ERROR testing {pattern_name}: {e}")
                    results[pattern_name].append({
                        'seed_doi': doi,
                        'seed_title': title,
                        'total_citing': total_citing,
                        'hit_count': 0,
                        'hit_rate': 0.0,
                        'error': str(e)
                    })

            time.sleep(0.2)  # Extra pause between seeds

        except Exception as e:
            print(f"  ERROR: {e}")
            continue

    return dict(results)


def main():
    # Paths
    papers_path = "/home/kyuwon/projects/papersift/results/virtual-cell-sweep/papers_cleaned.json"
    output_dir = Path("/home/kyuwon/projects/papersift/outputs/e002_v2")
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("E002: OpenAlex Fulltext Coverage & SOTA Filter Pattern Analysis")
    print("=" * 80)

    # Load papers
    print(f"\n[OBJECTIVE] Measure OpenAlex fulltext indexing coverage and filter pattern effectiveness")
    print(f"[DATA] Loading papers from {papers_path}")
    papers = load_papers(papers_path)
    print(f"[DATA] Loaded {len(papers)} papers")

    # Step 1: Fulltext coverage
    print("\n" + "=" * 80)
    print("STEP 1: Fulltext Indexing Coverage")
    print("=" * 80)

    dois = [p['doi'] for p in papers if 'doi' in p]
    print(f"[DATA] Checking {len(dois)} papers for fulltext availability")

    total_checked, fulltext_count = batch_check_fulltext(dois, batch_size=50)
    coverage_rate = fulltext_count / total_checked if total_checked > 0 else 0.0

    coverage_result = {
        'total_papers': len(papers),
        'total_checked': total_checked,
        'fulltext_available': fulltext_count,
        'coverage_rate': coverage_rate,
        'go_no_go': 'GO' if coverage_rate >= 0.30 else 'NO-GO'
    }

    print(f"\n[FINDING] Fulltext coverage: {fulltext_count}/{total_checked} = {100*coverage_rate:.1f}%")
    print(f"[STAT:n] n = {total_checked}")
    print(f"[STAT:rate] coverage_rate = {coverage_rate:.3f}")
    print(f"[DECISION] {coverage_result['go_no_go']} (threshold: 30%)")

    # Save coverage results
    coverage_path = output_dir / "fulltext_coverage.json"
    with open(coverage_path, 'w') as f:
        json.dump(coverage_result, f, indent=2)
    print(f"\n[OUTPUT] Coverage results saved to {coverage_path}")

    # Step 2: Filter pattern analysis
    print("\n" + "=" * 80)
    print("STEP 2: Text Filter Pattern Analysis")
    print("=" * 80)

    # Select diverse seeds: 1-2 papers per cluster (median-cited)
    import random
    random.seed(42)

    # Group by cluster if available, otherwise by topic
    clusters = {}
    for p in papers:
        # Use first topic as cluster proxy
        cluster_key = (p.get("topics", ["general"]) or ["general"])[0]
        clusters.setdefault(cluster_key, []).append(p)

    seed_papers = []
    for cluster_key, cluster_papers in sorted(clusters.items()):
        # Sort by citation count, pick median
        sorted_cp = sorted(cluster_papers, key=lambda x: x.get("cited_by_count", 0))
        median_idx = len(sorted_cp) // 2
        seed_papers.append(sorted_cp[median_idx])
        if len(seed_papers) >= 15:
            break

    # Ensure minimum 10 seeds
    if len(seed_papers) < 10:
        remaining = [p for p in papers if p not in seed_papers]
        remaining.sort(key=lambda x: x.get("cited_by_count", 0))
        median_start = len(remaining) // 3
        for p in remaining[median_start:]:
            if p not in seed_papers:
                seed_papers.append(p)
            if len(seed_papers) >= 15:
                break

    print(f"[DATA] Testing patterns on {len(seed_papers)} diverse seed papers (median-cited across topics):")
    for i, p in enumerate(seed_papers):
        print(f"  {i+1}. {p['title'][:60]}... (cited: {p.get('cited_by_count', 0)})")

    pattern_results = test_filter_patterns(seed_papers)

    # Aggregate statistics
    pattern_stats = {}
    for pattern_name, results_list in pattern_results.items():
        valid_results = [r for r in results_list if 'error' not in r and r['total_citing'] > 0]

        if valid_results:
            avg_hit_rate = sum(r['hit_rate'] for r in valid_results) / len(valid_results)
            total_hits = sum(r['hit_count'] for r in valid_results)
            total_citing = sum(r['total_citing'] for r in valid_results)

            pattern_stats[pattern_name] = {
                'avg_hit_rate': avg_hit_rate,
                'total_hits': total_hits,
                'total_citing': total_citing,
                'n_seeds': len(valid_results)
            }
        else:
            pattern_stats[pattern_name] = {
                'avg_hit_rate': 0.0,
                'total_hits': 0,
                'total_citing': 0,
                'n_seeds': 0
            }

    # Print summary
    print("\n" + "=" * 80)
    print("Pattern Performance Summary")
    print("=" * 80)
    print(f"{'Pattern':<25} {'Avg Hit Rate':<15} {'Total Hits':<12} {'Seeds':<8}")
    print("-" * 80)

    for pattern_name in ['method_proposal', 'sota_narrow', 'sota_broad', 'improvement', 'combined']:
        stats = pattern_stats[pattern_name]
        print(f"{pattern_name:<25} {stats['avg_hit_rate']:>6.1%}          "
              f"{stats['total_hits']:>8}      {stats['n_seeds']:>4}")

    print("\n[FINDING] Pattern effectiveness measured across seed papers")
    print(f"[STAT:n] n_seeds = {pattern_stats['method_proposal']['n_seeds']}")

    # Determine best pattern
    best_pattern = max(pattern_stats.items(), key=lambda x: x[1]['avg_hit_rate'])
    print(f"\n[FINDING] Best performing pattern: {best_pattern[0]}")
    print(f"[STAT:rate] avg_hit_rate = {best_pattern[1]['avg_hit_rate']:.3f}")

    # Save pattern results
    pattern_path = output_dir / "filter_patterns.json"
    with open(pattern_path, 'w') as f:
        json.dump({
            'pattern_stats': pattern_stats,
            'detailed_results': pattern_results
        }, f, indent=2)
    print(f"\n[OUTPUT] Pattern results saved to {pattern_path}")

    # Final summary
    print("\n" + "=" * 80)
    print("EXPERIMENT SUMMARY")
    print("=" * 80)
    print(f"1. Fulltext Coverage: {100*coverage_rate:.1f}% ({coverage_result['go_no_go']})")
    print(f"2. Best Pattern: {best_pattern[0]} ({100*best_pattern[1]['avg_hit_rate']:.1f}% avg hit rate)")
    print(f"3. Method vs SOTA: method_proposal {100*pattern_stats['method_proposal']['avg_hit_rate']:.1f}% "
          f"vs sota_narrow {100*pattern_stats['sota_narrow']['avg_hit_rate']:.1f}%")

    print(f"\n[LIMITATION] Analysis limited to top 10 cited papers; may not represent full dataset diversity")
    print(f"[LIMITATION] Pattern matching depends on fulltext availability and quality")


if __name__ == "__main__":
    main()
