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

## Next Steps (if GO)
1. Phase 2 schema extension (e005): Add `fulltext_url`, `fulltext_source` fields
2. Implement text extraction pipeline
3. Re-run LLM extraction with fulltext context
4. Measure improvement in method detection vs title+abstract baseline (e002)
