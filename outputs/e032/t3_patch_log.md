# T3 Patch Log — e032 OTR Definition Unification

## grep results
```
grep -rn "_compute_otr|off_topic|overused|corpus_prevalence" src/ scripts/
```

## Modified files

### 1. src/papersift/bridge_recommend.py
- **Pattern changed:** single-token proxy `len(e.split())==1 and "-" not in e and "/" not in e`
  → background_terms membership `e in bg`
- **Location:** `_compute_otr()` function (lines 96-118)
- **Fallback:** proxy retained when `background_terms=None`

### 2. scripts/e031_phase_c_validation.py
- **Pattern changed:** inline single-token OTR (`single_word = sum(...)`)
  → background_terms membership from bridge dict (`b.get("background_terms", None)`)
- **Fallback:** proxy retained when `background_terms` not in bridge dict

## Not modified
- `src/papersift/frontier.py`: `structural_gaps()` outputs `background_terms` as a list key (no OTR logic here)
- `src/papersift/cli.py`: OTR display only, no computation

## Definition standard
All OTR now uses: **corpus_prevalence membership** = entity is in `background_terms` set
(background_terms = entities appearing in ≥ adaptive_fraction of valid clusters)
