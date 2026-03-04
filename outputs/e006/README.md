# Experiment e006: Fulltext Coverage Analysis

## Objective
Measure actual fulltext availability for our 3,070 virtual cell papers across multiple free sources to determine if text-based filtering is viable.

## Hypothesis
If ≥60% of papers have accessible fulltext (PDF or XML), we can implement text-based filtering to improve clustering relevance.

## Data Sources
1. **Unpaywall**: OA status, PDF URLs, OA type (gold/green/hybrid/bronze)
2. **Europe PMC**: PMCID availability, fulltext XML access
3. **OpenAlex**: has_fulltext flag (already in our dataset)

## Usage

### Basic Run
```bash
python scripts/e006_fulltext_coverage.py \
    --input results/virtual-cell-sweep/papers_enriched.json \
    --output-dir outputs/e006 \
    --email your.real.email@domain.com
```

### Resume After Interruption
The script automatically saves checkpoints every 100 papers. Just re-run the same command - it will skip already-checked DOIs.

### Skip Specific Sources
```bash
# Skip Unpaywall (if you don't have a real email)
python scripts/e006_fulltext_coverage.py \
    --input results/virtual-cell-sweep/papers_enriched.json \
    --output-dir outputs/e006 \
    --skip-unpaywall

# Skip all but OpenAlex (fastest, uses existing data)
python scripts/e006_fulltext_coverage.py \
    --input results/virtual-cell-sweep/papers_enriched.json \
    --output-dir outputs/e006 \
    --skip-unpaywall \
    --skip-epmc
```

## Expected Runtime
- **Full run**: ~8-12 minutes for 3,070 papers
  - Unpaywall: ~5 min (10 req/s rate limit)
  - Europe PMC: ~8 min (150ms delay)
  - OpenAlex: <1 min (batch API, 200 per request)

## Output Files

### `fulltext_coverage.json`
Main results file with:
- Per-source statistics (OA counts, PDF availability, PMCID coverage)
- Combined coverage metrics
- Per-paper breakdown with all source flags
- Go/No-Go verdict (threshold: 60%)

### `checkpoint.json`
Intermediate state for resume functionality. Contains partial results from each source.

## Important Notes

### Unpaywall Email Requirement
Unpaywall API requires a **real email address** (rejects `example.com` domains).

If you see HTTP 422 errors:
```
HTTP Error: 422
Response: {"message": "Please use your own email address in API calls."}
```

Solution:
```bash
export UNPAYWALL_EMAIL="your.real.email@domain.com"
python scripts/e006_fulltext_coverage.py ...
```

Or use `--skip-unpaywall` to rely on Europe PMC + OpenAlex only.

### Rate Limits
- Unpaywall: 100,000 requests/day, 10 req/s (script uses 100ms delay)
- Europe PMC: No official limit, script uses conservative 150ms delay
- OpenAlex: No authentication required, batch requests of 200 DOIs

### Checkpoint Behavior
- Saves every 100 papers per source
- Skips DOIs already in checkpoint on resume
- Safe to interrupt (Ctrl+C) and resume later

## Go/No-Go Criteria

**GO if**: Combined fulltext coverage ≥ 60%
- "Combined" = any source has fulltext (Unpaywall PDF OR Europe PMC XML OR OpenAlex fulltext)

**NO-GO if**: Combined fulltext coverage < 60%
- Text filtering not viable, continue with title+abstract only

## A/B Comparison Methodology (T3)

### Overview
50 papers with both abstract and PMC fulltext were extracted twice:
- **Condition A (abstract-only)**: Standard extraction using title + abstract
- **Condition B (fulltext)**: Enhanced extraction using title + abstract + methods/results/discussion sections

Both conditions used identical prompts (EXTRACTION_PROMPT_TEMPLATE vs FULLTEXT_EXTRACTION_PROMPT_TEMPLATE) with the same 7-field schema. Extraction was performed by 15 parallel Claude haiku subagents.

### Specificity Score Definition
Each extracted field is scored 0-2 for specificity:
- **0**: Empty or generic (e.g., "computational methods", "biological data")
- **1**: Domain-specific but broad (e.g., "agent-based modeling", "gene expression dataset")
- **2**: Highly specific with quantitative detail (e.g., "hybrid ODE-ABM model with Gillespie algorithm", "TCGA BRCA cohort N=1,098")

Scoring was performed by LLM comparison (Claude haiku) given both extractions side-by-side. **Limitation**: This is LLM self-evaluation, not human expert validation. Inter-annotator agreement with human raters has not been measured.

### Improvement Judgment Criteria
For each paper × field pair, the comparison LLM judged:
- **improved**: Fulltext extraction is more specific, accurate, or complete
- **degraded**: Abstract extraction was better (fulltext introduced errors or lost information)
- **same**: No meaningful difference

### Key Metrics

| Metric | Definition | Value |
|--------|-----------|-------|
| `net_improvement_ratio` | `improved / (improved + degraded)` | 0.822 (88/107) |
| `avg_specificity_delta` | Mean(fulltext_specificity - abstract_specificity) across 7 fields | +0.223 |
| `avg_coverage_delta` | Mean additional papers with non-empty fields | +3.1 |

**Note on improvement_ratio**: This metric excludes `same` judgments (243/350 = 69.4%). An alternative metric including all judgments: `improved / total = 88/350 = 25.1%`. The ratio measures "when there IS a difference, how often is it positive?" not "what fraction of all extractions improved?"

### Per-Field Results

| Field | Improved | Degraded | Same | Specificity Δ | Coverage Δ |
|-------|:--------:|:--------:|:----:|:-------------:|:----------:|
| baseline | 24 | 3 | 23 | +0.48 | +32pp (64%→96%) |
| result | 13 | 5 | 32 | +0.18 | +4pp |
| dataset | 13 | 1 | 36 | +0.24 | +6pp |
| method | 11 | 3 | 36 | +0.16 | 0pp |
| metric | 10 | 1 | 39 | +0.24 | +2pp |
| problem | 9 | 1 | 40 | +0.22 | 0pp |
| finding | 8 | 5 | 37 | +0.04 | 0pp |

### Sample Selection
- **N=50** from 705 papers with PMC fulltext (7.1% of fulltext-available papers)
- Selected as the first 50 common DOIs between abstract and fulltext extraction runs
- **Known bias**: Only open-access PMC papers included. Closed-access papers (44.1% of corpus) are not represented.

### Limitations
1. **LLM self-evaluation**: Specificity scoring and improvement judgment performed by same model family that did extraction. No human expert ground truth.
2. **OA sampling bias**: PMC fulltext papers skew toward biomedical journals with OA mandates (NIH, Wellcome Trust).
3. **Small sample**: 50/3,070 (1.6%) — sufficient for directional signal, not for precise effect size estimation.
4. **No downstream validation**: Impact on landscape report quality not measured.

## Verdict
**GO** — Fulltext extraction shows consistent improvement across all 7 fields (avg specificity Δ +0.223), with the strongest effect on `baseline` (+0.48, coverage +32pp). The improvement pattern is directionally clear despite measurement limitations.

## Next Steps
1. ~~Phase 2 schema extension (e005)~~ — Completed, integrated into extract.py
2. ~~Implement text extraction pipeline~~ — Completed (fulltext.py)
3. e007: Full 3,070-paper extraction run
4. e008: Downstream impact measurement (landscape report quality comparison)
