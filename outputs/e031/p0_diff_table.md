# e031 P0b/P0c — Bridge Comparison (alphabetical → b-potential)

**Date**: 2026-04-07  
**Source**: outputs/e028/bridge_candidates.json (old) vs frontier.run_pipeline (new, T1 commit 2676a73)

## Aggregate

| Metric | Old (alphabetical) | New (b-potential) |
|---|---|---|
| OTR ≤ 0.40 PASS rate | 14/19 (73.7%) | **19/19 (100.0%)** |
| Combined eval PASS (OTR≤0.40 ∧ CCR≥0.30) | 0/19 | **0/19** |
| **P0c automated gate** (≥50% OTR PASS) | — | **PASS ✓** |

## Per-domain breakdown

### AMR (9 bridges)
- OTR≤0.40: old 4/9 (44%) → new 9/9 (100%)

### NEUROSCIENCE (10 bridges)
- OTR≤0.40: old 10/10 (100%) → new 10/10 (100%)

## Spot-check table — top-3 bridges per domain

For each, eyeball whether the new top-5 are more domain-specific than the old.

| ID | Domain | Pair | Old top-5 (alphabetical) | New top-5 (b-potential) | Old OTR / CCR | New OTR / CCR |
|---|---|---|---|---|---|---|
| B01 | amr | C4 <-> C5 | america, antibiotic, antibiotics, antimicrobial, bacteria | **surveillance, states, united, epidemiology, eskape** | 0.6 / 0.0 | **0.0 / 0.0** |
| B02 | amr | C0 <-> C2 | action, active, antibiotic, antibiotics, antimicrobial | **drug, biofilms, biofilm, multidrug, therapeutic** | 0.4 / 0.0 | **0.0 / 0.0** |
| B03 | amr | C0 <-> C4 | action, antibiotic, antibiotics, antimicrobial, bacteria | **klebsiella, escherichia, escherichia coli, global, salmonella** | 0.6 / 0.0 | **0.0 / 0.2** |
| B11 | neuroscience | C9 <-> C10 | ca1, hippocampal, long-term, ltp, memory | **ca1, ltp, synaptic, hippocampal, long-term** | 0.2 / 0.2 | **0.2 / 0.2** |
| B12 | neuroscience | C1 <-> C2 | ampa, arc, calcium, consolidation, creb | **long-term, synaptic, plasticity, hippocampal, memory** | 0.0 / 0.0 | **0.4 / 0.2** |
| B13 | neuroscience | C9 <-> C11 | ca1, hippocampus, ltp, memory, nmda | **nmda, memory, ca1, ltp, receptor** | 0.2 / 0.0 | **0.2 / 0.0** |