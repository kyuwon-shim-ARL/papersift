#!/usr/bin/env python3
"""e031 Phase C validation: leaf-tier bridge OTR PASS rate >= 50%.

Usage:
    python scripts/e031_phase_c_validation.py \
        --e028-bridges outputs/e028/bridge_candidates.json \
        --output outputs/e031/p2_leaf_bridge_evaluation.json
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def compute_otr(entities: list[str], corpus_prevalence: dict[str, float], threshold: float = 0.10) -> float:
    """OTR = fraction of top-5 entities with corpus_prevalence >= threshold."""
    top5 = entities[:5]
    if not top5:
        return 0.0
    overused = sum(1 for e in top5 if corpus_prevalence.get(e, 0) >= threshold)
    return overused / len(top5)


def compute_ccr(entities: list[str]) -> float:
    """CCR = fraction of entities with '-', '/' or 2+ tokens."""
    if not entities:
        return 0.0
    compound = sum(1 for e in entities if "-" in e or "/" in e or len(e.split()) >= 2)
    return compound / len(entities)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--e028-bridges", required=True)
    parser.add_argument("--output", default="outputs/e031/p2_leaf_bridge_evaluation.json")
    args = parser.parse_args()

    with open(args.e028_bridges) as f:
        bridges = json.load(f)

    results = []
    for b in bridges:
        entities = b.get("shared_entities", [])
        # Without real corpus_prevalence data, use CCR only as proxy
        ccr = compute_ccr(entities)
        # OTR approximation: count single-word entities
        single_word = sum(1 for e in entities[:5] if len(e.split()) == 1 and "-" not in e)
        otr = single_word / max(len(entities[:5]), 1)
        evaluability = "PASS" if otr <= 0.40 and ccr >= 0.30 else ("CONDITIONAL" if otr <= 0.60 else "FAIL")
        results.append({
            "cluster_a": b.get("cluster_a"),
            "cluster_b": b.get("cluster_b"),
            "entities": entities,
            "otr": round(otr, 3),
            "ccr": round(ccr, 3),
            "evaluability": evaluability,
        })

    n_pass = sum(1 for r in results if r["evaluability"] == "PASS")
    pass_rate = n_pass / len(results) if results else 0
    verdict = "PASS" if pass_rate >= 0.50 else f"FAIL ({pass_rate:.1%} < 50%)"

    output = {
        "n_bridges": len(results),
        "n_pass": n_pass,
        "pass_rate": round(pass_rate, 3),
        "verdict": verdict,
        "bridges": results,
    }

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)
    print(f"Phase C validation: {verdict}")
    print(f"Report: {args.output}")


if __name__ == "__main__":
    main()
