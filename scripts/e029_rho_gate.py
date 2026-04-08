#!/usr/bin/env python3
"""e029 T2: rho gate — measure correlation between entity Jaccard and cosine similarity."""

import json
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from papersift.entity_layer import compute_rho_gate

DATA = "results/gut-microbiome-sweep/papers.json"
OUTPUT = "outputs/e029/t2_rho_gate.json"


def main():
    with open(DATA) as f:
        papers = json.load(f)

    print(f"Running rho gate on {len(papers)} papers (best arm: topics-only)...")
    result = compute_rho_gate(
        papers,
        use_topics=True,  # best arm from T1
        n_samples=500,
        seed=42,
    )

    output = {
        "experiment": "e029-T2",
        "dataset": DATA,
        "n_papers": len(papers),
        "best_arm": "A_topics_only",
        "rho": result.get("rho"),
        "p_value": result.get("p_value"),
        "decision": result.get("decision"),
        "reason": result.get("reason"),
        "gate_ranges": {
            "GO": "0.3 <= rho <= 0.7",
            "SKIP_low": "rho < 0.3 (dilution risk)",
            "SKIP_high": "rho > 0.7 (redundant)",
        },
        "note": "T2 SKIP does not affect e029 verdict. Phase 4 conditional only.",
    }

    with open(OUTPUT, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"\nrho = {result.get('rho'):.4f}, p = {result.get('p_value'):.4e}")
    print(f"Decision: {result.get('decision')} — {result.get('reason')}")
    print(f"Results saved to {OUTPUT}")


if __name__ == "__main__":
    main()
