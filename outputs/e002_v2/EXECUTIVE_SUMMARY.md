# E002 v2: OpenAlex Fulltext Coverage & SOTA Filter Pattern Analysis

## Verdict: NO-GO

## Background
E002 tests whether OpenAlex fulltext search can be used to filter SOTA/methodological papers from citing paper sets. The original v1 experiment reported GO (48.6% coverage, 29.7% hit rate), but was invalidated due to three bugs:
1. `.search()` searched title+abstract+fulltext combined (not fulltext-only)
2. Default `per_page=25` checked only 50.3% of papers
3. Seed selection biased toward mega-cited papers

## v2 Corrections
- `fulltext.search` filter for fulltext-only matching
- `.get(per_page=200)` for complete DOI batch coverage
- 15 median-cited seeds across diverse topic clusters

## Key Results

### Fulltext Coverage: 24.5% (NO-GO)
- 751 / 3,062 papers have fulltext indexed in OpenAlex
- Below the 30% threshold for viable filtering strategy
- v1 reported 48.6% on a partial sample — nearly 2x inflation

### Pattern Hit Rates (avg across 15 seeds)

| Pattern | Avg Hit Rate | Total Hits | v1 Rate | Delta |
|---------|-------------|------------|---------|-------|
| improvement | 16.1% | 1,366 | 29.7% | -13.6pp |
| method_proposal | 11.3% | 1,070 | 26.8% | -15.5pp |
| combined | 4.6% | 682 | N/A | — |
| sota_narrow | 4.3% | 168 | 7.8% | -3.5pp |
| sota_broad | 3.8% | 306 | N/A | — |

### Key Observations
1. **"improvement" is the best single pattern** (16.1%) but insufficient for reliable filtering
2. **Combined patterns underperform** individual patterns (4.6% < 16.1%), likely due to OR-clause matching across unrelated contexts
3. **SOTA-specific patterns are weak** (3.8-4.3%) — few papers use explicit "outperforms" / "state-of-the-art" language in fulltext
4. **Low-citation seeds show near-zero hits** — fulltext filtering is biased toward well-cited paper chains

## Implications
1. OpenAlex fulltext search is NOT viable as a primary paper discovery/filtering strategy
2. The abstract+LLM extraction pipeline (PaperSift v0.3.0) remains the best approach
3. E005 Phase 2 (OA full-text extraction for deeper metadata) is deprioritized
4. Future SOTA detection should rely on LLM extraction from abstracts, not keyword matching in fulltext

## Data
- `fulltext_coverage.json`: coverage statistics
- `filter_patterns.json`: per-seed pattern results
- Script: `scripts/e002_fulltext_coverage.py`
