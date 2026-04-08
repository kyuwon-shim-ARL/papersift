"""e031 — Regenerate e026/bridge_evaluation.csv with b-potential entities.

Loads e028 bridge_candidates.json (has cluster labels, bridge_scores, IDs),
runs frontier.structural_gaps with new b-potential+stoplist code on each domain,
replaces shared_entities with new top-8, writes updated CSV and JSON.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from papersift.frontier import extract_entities, structural_gaps

DOMAINS = [
    ("amr", "results/amr-sweep"),
    ("ai-foundation", "results/ai-foundation-sweep"),
    ("neuroscience", "results/neuroscience-sweep"),
]

OLD_CANDIDATES = Path("outputs/e028/bridge_candidates.json")
OUT_CSV = Path("outputs/e026/bridge_evaluation.csv")
OUT_JSON = Path("outputs/e031/bridge_candidates_bpot.json")
OUT_JSON.parent.mkdir(parents=True, exist_ok=True)


def run_domain(domain: str, sweep_dir: str) -> dict:
    papers = json.loads(Path(f"{sweep_dir}/papers.json").read_text())
    clusters = json.loads(Path(f"{sweep_dir}/clusters.json").read_text())
    print(f"[{domain}] {len(papers)} papers, {len(clusters)} cluster assignments")
    entity_data = extract_entities(papers)
    entity_data = {k: set(v) if not isinstance(v, set) else v for k, v in entity_data.items()}
    result = structural_gaps(papers, entity_data, clusters)
    # index by (ca, cb) normalized so ca < cb
    index: dict[tuple, dict] = {}
    for b in result["cross_cluster_bridges"]:
        ca, cb = str(b["cluster_a"]), str(b["cluster_b"])
        if int(ca) > int(cb):
            ca, cb = cb, ca
        index[(ca, cb)] = b
    bg = result.get("background_terms", [])
    print(f"  background_terms filtered: {len(bg)}")
    return index


def parse_pair(entity_pair: str) -> tuple[str, str] | None:
    m = re.match(r"C?(\d+)\s*<->\s*C?(\d+)", entity_pair)
    if not m:
        return None
    ca, cb = m.group(1), m.group(2)
    if int(ca) > int(cb):
        ca, cb = cb, ca
    return ca, cb


def main():
    old = json.loads(OLD_CANDIDATES.read_text())
    print(f"Loaded {len(old)} bridge candidates from e028")

    # Domain name aliases (e028 used "ai", pipeline uses "ai-foundation")
    DOMAIN_ALIASES = {"ai-foundation": "ai", "ai": "ai-foundation"}

    # Run new b-potential pipeline per domain
    domain_index: dict[str, dict] = {}
    for domain, sweep_dir in DOMAINS:
        result = run_domain(domain, sweep_dir)
        domain_index[domain] = result
        if domain in DOMAIN_ALIASES:
            domain_index[DOMAIN_ALIASES[domain]] = result

    updated = []
    matched = 0
    for b in old:
        domain = b["domain"]
        pair = parse_pair(b.get("entity_pair", ""))
        nb = domain_index.get(domain, {}).get(pair) if pair else None
        if nb is not None:
            new_shared = nb["shared_entities"][:8]
            matched += 1
        else:
            new_shared = b["shared_entities"]  # fallback: keep old
            print(f"  WARN: no match for {b['bridge_id']} ({domain} {b.get('entity_pair')})")
        updated.append({**b, "shared_entities": new_shared})

    print(f"\nMatched and updated: {matched}/{len(old)}")

    # Write updated JSON
    OUT_JSON.write_text(json.dumps(updated, indent=2))
    print(f"Wrote {OUT_JSON}")

    # Write CSV (same columns as original e026)
    fieldnames = [
        "bridge_id", "domain", "type", "source_cluster", "target_cluster",
        "shared_entities (top 8)", "shared_count", "bridge_score",
        "novelty (1-5)", "feasibility (1-5)", "overall_interest (1-5)",
        "relevance (0/1)", "notes",
    ]
    rows = []
    for b in updated:
        rows.append({
            "bridge_id": b["bridge_id"],
            "domain": b["domain"],
            "type": b["type"],
            "source_cluster": b["source_cluster"],
            "target_cluster": b["target_cluster"],
            "shared_entities (top 8)": ", ".join(b["shared_entities"]),
            "shared_count": b["shared_count"],
            "bridge_score": b["bridge_score"],
            "novelty (1-5)": b.get("novelty_score") or "",
            "feasibility (1-5)": b.get("feasibility_score") or "",
            "overall_interest (1-5)": b.get("overall_interest") or "",
            "relevance (0/1)": b.get("relevance_binary") or "",
            "notes": b.get("notes") or "",
        })

    with OUT_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {OUT_CSV}")


if __name__ == "__main__":
    main()
