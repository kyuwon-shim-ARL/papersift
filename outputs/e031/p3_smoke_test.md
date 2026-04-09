# e031 Phase D Smoke Test Report

## Setup
- Dataset: virtual-cell-sweep
- Top-level clusters: 11 (clusters 0-10)
- Sub-clustered: ['0', '1', '5'] (size > 200)
- Total leaf sub-clusters: 374
- Total partitions in pipeline: 382

## Two-Tier Bridge Output

### Tier 1 — Top-level bridges (legacy, backward compat)

- **C2 ↔ C4**: virtual, manufacturing, simulation, production, optimization (OTR=1.0, FAIL)
- **C4 ↔ C6**: digital twin, fuel, battery, pem, simulation (OTR=0.8, FAIL)
- **C3 ↔ C7**: human, mouse, response, stem cell, role (OTR=0.8, FAIL)
- **C3 ↔ C6**: dynamics, whole, blood, membrane, simulation (OTR=1.0, FAIL)
- **C2 ↔ C3**: human, simulation, design, dynamics, culture (OTR=1.0, FAIL)

### Tier 2 — Leaf-level bridges (cross_parent filter)

- **0.0 ↔ 3**: human, disease, proliferation, dynamics, simulation (OTR=1.0, CCR=0.167, FAIL)
- **0.0 ↔ 7**: cancer, t cell, human, proliferation (OTR=0.75, CCR=0.25, FAIL)
- **0.2 ↔ 7**: human, development, stem cell (OTR=0.667, CCR=0.333, FAIL)
- **1.2 ↔ 3**: disease, mouse, single-cell, stem, agent-based (OTR=0.6, CCR=0.4, CONDITIONAL)
- **1.2 ↔ 7**: agent-based, mouse, cancer (OTR=0.667, CCR=0.333, FAIL)
- **5.6 ↔ 7**: development, human (OTR=1.0, CCR=0.0, FAIL)
- **0.9 ↔ 7**: effects, immune (OTR=1.0, CCR=0.0, FAIL)
- **5.3 ↔ 7**: response, cancer (OTR=1.0, CCR=0.0, FAIL)
- **5.0 ↔ 6**: multiscale, mathematical, mechanics, optimization (OTR=1.0, CCR=0.0, FAIL)

## OTR/CCR Evaluability Summary

- Total recommendations: 19
- PASS (OTR≤0.40 AND CCR≥0.30): 0 (0%)
- CONDITIONAL: 1 (5%)
- FAIL: 13 (68%)

## Verdict: CONDITIONAL

## Sanity Check — Are leaf bridges domain-specific?

Top 5 leaf cross-cluster bridge entities (should be compound/specific, NOT single generic words):

  - 4 ↔ 6: **digital twin, li-ion**
  - 3 ↔ 7: **stem cell, agent-based**
  - 3 ↔ 6: **whole-cell**
  - 0.0 ↔ 3: **tumor cell**
  - 0.0 ↔ 7: **t cell**