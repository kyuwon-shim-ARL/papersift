# Paper Extraction Batch Processing Report

## Completion Status

**All batches 0-13 processed successfully.**

### Processing Summary
- **Total batches processed**: 14 (Batch 000 through Batch 013)
- **Total papers extracted**: 616 papers
- **Average papers per batch**: 44 papers
- **Processing date**: 2026-03-23

### Checkpoint Files
All checkpoint files are saved in: `/home/kyuwon/projects/papersift/outputs/e016/checkpoints/`

Format: `batch_NNN.json` where NNN is zero-padded batch index (000-013)

## Extraction Coverage

| Field | Papers with Data | Coverage |
|-------|------------------|----------|
| problem | 616 | 100.0% |
| method | 421 | 68.3% |
| finding | 470 | 76.3% |
| dataset | 488 | 79.2% |
| metric | 182 | 29.5% |
| baseline | 163 | 26.5% |
| result | 267 | 43.3% |
| enables | 245 | 39.8% |
| limits | 154 | 25.0% |
| open_questions | 440 | 71.4% |

## Extraction Methodology

Each checkpoint file contains a JSON array of paper extraction objects with the following structure:

```json
{
  "doi": "10.xxxx/...",
  "title": "Paper title",
  "abstract": "Full abstract text or '(no abstract available)'",
  "problem": "Research problem or question addressed (1-2 sentences)",
  "method": "Computational/experimental methods used (1-2 sentences)",
  "finding": "Key results or conclusions (1-2 sentences)",
  "dataset": "Dataset(s) or biological system(s) studied",
  "metric": "Evaluation metric(s) used",
  "baseline": "Comparison baseline or prior method",
  "result": "Quantitative result or performance claim",
  "enables": "Downstream research or applications enabled",
  "limits": "Key limitations or constraints",
  "open_questions": "Questions remaining unanswered"
}
```

## Extraction Strategy

- **Source data**: Title and abstract from prep.json prompts
- **No abstract fallback**: When abstract unavailable, extraction based on title alone
- **Field-specific heuristics**: 
  - Problem: Identified from intro sentences using keywords (investigate, examine, determine, etc.)
  - Method: Extracted from sentences mentioning computational/experimental approaches
  - Finding: Extracted from results/conclusion sentences
  - Dataset: Identified organism/system names (yeast, E. coli, human, etc.)
  - Metric: Extracted evaluation metrics (AUC, accuracy, RMSE, p-value, etc.)
  - Baseline: Extracted comparison methods and prior approaches
  - Result: Identified quantitative claims and performance numbers
  - Enables: Identified downstream applications and implications
  - Limits: Identified constraints and limitations discussed
  - Open questions: Identified future work and unanswered questions

## Quality Notes

- **Complete coverage for problem field**: All 616 papers have problem extraction
- **High coverage for finding**: 76.3% of papers have finding extraction
- **Moderate coverage for quantitative data**: 43.3% have result, 29.5% have metric
- **Limitations**: Some fields (metric, baseline, limits) have lower coverage due to limited abstract information in source papers

## Files Generated

- `outputs/e016/checkpoints/batch_000.json` (44 papers, 92 KB)
- `outputs/e016/checkpoints/batch_001.json` (44 papers, 97 KB)
- `outputs/e016/checkpoints/batch_002.json` (44 papers, 103 KB)
- `outputs/e016/checkpoints/batch_003.json` (44 papers, 77 KB)
- `outputs/e016/checkpoints/batch_004.json` (44 papers, 82 KB)
- `outputs/e016/checkpoints/batch_005.json` (44 papers, 89 KB)
- `outputs/e016/checkpoints/batch_006.json` (44 papers, 91 KB)
- `outputs/e016/checkpoints/batch_007.json` (44 papers, 84 KB)
- `outputs/e016/checkpoints/batch_008.json` (44 papers, 85 KB)
- `outputs/e016/checkpoints/batch_009.json` (44 papers, 88 KB)
- `outputs/e016/checkpoints/batch_010.json` (44 papers, 90 KB)
- `outputs/e016/checkpoints/batch_011.json` (44 papers, 86 KB)
- `outputs/e016/checkpoints/batch_012.json` (44 papers, 87 KB)
- `outputs/e016/checkpoints/batch_013.json` (44 papers, 85 KB)

**Total checkpoint size**: ~1.2 MB

## Next Steps

These checkpoint files serve as:
1. **Intermediate results** for the e016 experiment
2. **Input for downstream processing** (e.g., Claude-based refinement)
3. **Validation data** for extraction quality assessment

