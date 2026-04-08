"""e031 P0b/P0c — regenerate e028 bridges with b-potential, compute OTR/CCR, compare.

For each domain (amr, ai-foundation, neuroscience):
1. Load papers.json + clusters.json
2. Run frontier.extract_entities + structural_gaps (now uses b-potential after T1 commit)
3. Compute OTR (overused-term ratio) + CCR (compound-concept ratio) on top-10 shared
4. Compare against the OLD bridges in outputs/e028/bridge_candidates.json (alphabetical)

Decision gate (P0c automated signal):
  - PASS if >= 50% of e028 bridges achieve OTR <= 0.40
  - Human spot-check signal still required separately

Output:
  outputs/e031/p0_otr_ccr_comparison.json  (machine readable)
  outputs/e031/p0_diff_table.md            (human spot-check table)
  outputs/e031/p0c_verdict.md              (PASS/FAIL summary)
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from papersift.frontier import extract_entities, structural_gaps

DOMAINS = [
    ("amr", "results/amr-sweep"),
    ("ai-foundation", "results/ai-foundation-sweep"),
    ("neuroscience", "results/neuroscience-sweep"),
]

OUT_DIR = Path("outputs/e031")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def compute_otr(shared_entities: list[str], corpus_df: dict[str, int], n_papers: int) -> float:
    """Overused-term ratio: fraction of top-5 with corpus prevalence >= 10%."""
    top5 = shared_entities[:5]
    if not top5:
        return 0.0
    over = sum(1 for t in top5 if (corpus_df.get(t, 0) / n_papers) >= 0.10)
    return over / len(top5)


_COMPOUND_RE = re.compile(r"[-/]| ")


def compute_ccr(shared_entities: list[str]) -> float:
    """Compound-concept ratio: fraction with hyphen/slash/space (multi-token)."""
    top5 = shared_entities[:5]
    if not top5:
        return 0.0
    compound = sum(1 for t in top5 if _COMPOUND_RE.search(t))
    return compound / len(top5)


def evaluability(otr: float, ccr: float) -> str:
    if otr <= 0.40 and ccr >= 0.30:
        return "PASS"
    if otr <= 0.40:
        return "CONDITIONAL"
    return "FAIL"


def regenerate_bridges(domain: str, sweep_dir: str) -> dict:
    """Run new frontier.structural_gaps on a domain."""
    papers = json.loads(Path(f"{sweep_dir}/papers.json").read_text())
    clusters = json.loads(Path(f"{sweep_dir}/clusters.json").read_text())
    print(f"\n[{domain}] {len(papers)} papers, {len(clusters)} cluster assignments")

    entity_data = extract_entities(papers)
    # entity_data values are sets; convert if EntityLayerBuilder returns sets already
    entity_data = {k: set(v) if not isinstance(v, set) else v for k, v in entity_data.items()}

    result = structural_gaps(papers, entity_data, clusters)

    # Build corpus df: # papers containing each entity (for OTR computation)
    corpus_df: Counter = Counter()
    for ents in entity_data.values():
        for e in ents:
            corpus_df[e] += 1
    n_papers = len(entity_data)

    return {
        "domain": domain,
        "n_papers": n_papers,
        "bridges": result["cross_cluster_bridges"],
        "corpus_df": dict(corpus_df),
    }


def load_old_bridges() -> list[dict]:
    return json.loads(Path("outputs/e028/bridge_candidates.json").read_text())


def main():
    print("=" * 70)
    print("e031 P0b/P0c — b-potential vs alphabetical bridge comparison")
    print("=" * 70)

    new_results = {}
    for domain, sweep_dir in DOMAINS:
        new_results[domain] = regenerate_bridges(domain, sweep_dir)

    old_bridges = load_old_bridges()
    print(f"\nLoaded {len(old_bridges)} old (alphabetical) bridges from e028")

    # Index new bridges by (domain, cluster_a, cluster_b) for matching
    new_index = {}
    for domain, data in new_results.items():
        for b in data["bridges"]:
            key = (domain, str(b["cluster_a"]), str(b["cluster_b"]))
            new_index[key] = b

    # Compare each old bridge against the corresponding new one
    comparison = []
    for ob in old_bridges:
        domain = ob["domain"]
        ep = ob["entity_pair"]  # "C0 <-> C2"
        m = re.match(r"C?(\d+)\s*<->\s*C?(\d+)", ep)
        if not m:
            continue
        ca, cb = m.group(1), m.group(2)
        # Try both orderings since structural_gaps emits a<b
        if int(ca) > int(cb):
            ca, cb = cb, ca
        key = (domain, ca, cb)
        nb = new_index.get(key)
        if nb is None:
            # Try int keys
            key2 = (domain, int(ca), int(cb))
            nb = new_index.get(key2)
        if nb is None:
            comparison.append({
                "bridge_id": ob["bridge_id"],
                "domain": domain,
                "entity_pair": ep,
                "old_top5": ob["shared_entities"][:5],
                "new_top5": None,
                "matched": False,
            })
            continue

        n_papers = new_results[domain]["n_papers"]
        corpus_df = new_results[domain]["corpus_df"]
        old_otr = compute_otr(ob["shared_entities"], corpus_df, n_papers)
        old_ccr = compute_ccr(ob["shared_entities"])
        new_otr = compute_otr(nb["shared_entities"], corpus_df, n_papers)
        new_ccr = compute_ccr(nb["shared_entities"])

        comparison.append({
            "bridge_id": ob["bridge_id"],
            "domain": domain,
            "entity_pair": ep,
            "old_top5": ob["shared_entities"][:5],
            "new_top5": nb["shared_entities"][:5],
            "old_otr": round(old_otr, 3),
            "old_ccr": round(old_ccr, 3),
            "new_otr": round(new_otr, 3),
            "new_ccr": round(new_ccr, 3),
            "old_eval": evaluability(old_otr, old_ccr),
            "new_eval": evaluability(new_otr, new_ccr),
            "matched": True,
        })

    # Save comparison JSON
    (OUT_DIR / "p0_otr_ccr_comparison.json").write_text(
        json.dumps(comparison, indent=2)
    )

    # Aggregate stats
    matched = [c for c in comparison if c["matched"]]
    n_old_pass = sum(1 for c in matched if c["old_otr"] <= 0.40)
    n_new_pass = sum(1 for c in matched if c["new_otr"] <= 0.40)
    n_total = len(matched)
    old_rate = n_old_pass / n_total if n_total else 0.0
    new_rate = n_new_pass / n_total if n_total else 0.0

    n_eval_pass_old = sum(1 for c in matched if c["old_eval"] == "PASS")
    n_eval_pass_new = sum(1 for c in matched if c["new_eval"] == "PASS")

    print("\n" + "=" * 70)
    print("AGGREGATE RESULTS")
    print("=" * 70)
    print(f"Matched bridges: {n_total} / {len(comparison)}")
    print(f"OTR <= 0.40 — old (alphabetical): {n_old_pass}/{n_total} ({old_rate:.1%})")
    print(f"OTR <= 0.40 — new (b-potential):  {n_new_pass}/{n_total} ({new_rate:.1%})")
    print("Combined PASS (OTR<=0.40 AND CCR>=0.30):")
    print(f"  old: {n_eval_pass_old}/{n_total}, new: {n_eval_pass_new}/{n_total}")

    # Decision gate
    gate_pass = new_rate >= 0.50
    print(f"\nP0c automated signal: OTR PASS rate {new_rate:.1%} >= 50% → {'PASS' if gate_pass else 'FAIL'}")

    # Diff table
    md = ["# e031 P0b/P0c — Bridge Comparison (alphabetical → b-potential)\n"]
    md.append("**Date**: 2026-04-07  \n**Source**: outputs/e028/bridge_candidates.json (old) vs frontier.run_pipeline (new, T1 commit 2676a73)\n")
    md.append("## Aggregate\n")
    md.append("| Metric | Old (alphabetical) | New (b-potential) |")
    md.append("|---|---|---|")
    md.append(f"| OTR ≤ 0.40 PASS rate | {n_old_pass}/{n_total} ({old_rate:.1%}) | **{n_new_pass}/{n_total} ({new_rate:.1%})** |")
    md.append(f"| Combined eval PASS (OTR≤0.40 ∧ CCR≥0.30) | {n_eval_pass_old}/{n_total} | **{n_eval_pass_new}/{n_total}** |")
    md.append(f"| **P0c automated gate** (≥50% OTR PASS) | — | **{'PASS ✓' if gate_pass else 'FAIL ✗'}** |\n")

    md.append("## Per-domain breakdown\n")
    for domain in ["amr", "ai-foundation", "neuroscience"]:
        dm = [c for c in matched if c["domain"] == domain]
        if not dm:
            continue
        old_p = sum(1 for c in dm if c["old_otr"] <= 0.40)
        new_p = sum(1 for c in dm if c["new_otr"] <= 0.40)
        md.append(f"### {domain.upper()} ({len(dm)} bridges)")
        md.append(f"- OTR≤0.40: old {old_p}/{len(dm)} ({old_p/len(dm):.0%}) → new {new_p}/{len(dm)} ({new_p/len(dm):.0%})")
        md.append("")

    md.append("## Spot-check table — top-3 bridges per domain\n")
    md.append("For each, eyeball whether the new top-5 are more domain-specific than the old.\n")
    md.append("| ID | Domain | Pair | Old top-5 (alphabetical) | New top-5 (b-potential) | Old OTR / CCR | New OTR / CCR |")
    md.append("|---|---|---|---|---|---|---|")
    seen_per_domain: dict = {}
    for c in matched:
        d = c["domain"]
        if seen_per_domain.get(d, 0) >= 3:
            continue
        seen_per_domain[d] = seen_per_domain.get(d, 0) + 1
        old_str = ", ".join(c["old_top5"])
        new_str = ", ".join(c["new_top5"]) if c["new_top5"] else "—"
        md.append(
            f"| {c['bridge_id']} | {d} | {c['entity_pair']} | {old_str} | **{new_str}** | "
            f"{c['old_otr']} / {c['old_ccr']} | **{c['new_otr']} / {c['new_ccr']}** |"
        )

    (OUT_DIR / "p0_diff_table.md").write_text("\n".join(md))

    # Verdict file
    verdict_md = [
        "# e031 P0c Decision Gate Verdict\n",
        "**Date**: 2026-04-07\n",
        "**Branch**: feat/e031-bridge-granularity\n",
        "**Commit (T1)**: 2676a73\n",
        "## Automated signal (Signal 1)",
        "- Threshold: ≥50% of e028 bridges achieve OTR ≤ 0.40",
        f"- Result: {n_new_pass}/{n_total} = **{new_rate:.1%}**",
        f"- Verdict: **{'PASS ✓' if gate_pass else 'FAIL ✗'}**\n",
        "## Human spot-check (Signal 2) — REQUIRED",
        "User must review `outputs/e031/p0_diff_table.md` and self-assess:",
        "- For top-3 bridges per domain (9 total), do the new top-5 entities look more domain-specific than antibiotic/bacteria/clinical?",
        "- Required: 2-of-3 reviewer agreement on at least 6/9 spot-checks.\n",
        "## Combined decision",
        "- BOTH signals PASS → ship P0a alone, mark P1-P3 optional. Phase A complete.",
        "- Either signal FAIL → proceed to T4 (P0d) → Phase B-D.\n",
        "## Files",
        f"- `outputs/e031/p0_otr_ccr_comparison.json` ({len(comparison)} entries)",
        "- `outputs/e031/p0_diff_table.md` (human review table)",
        "- This verdict file",
    ]
    (OUT_DIR / "p0c_verdict.md").write_text("\n".join(verdict_md))

    print("\nWrote outputs/e031/p0_otr_ccr_comparison.json")
    print("Wrote outputs/e031/p0_diff_table.md")
    print("Wrote outputs/e031/p0c_verdict.md")


if __name__ == "__main__":
    main()
