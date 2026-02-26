# E002 v2: Re-experiment with Bug Fixes

## Bugs Fixed
1. **`.search()` → `fulltext.search`**: v1 used `.search()` which searches title+abstract+fulltext combined. v2 uses `fulltext.search` filter for fulltext-only matching.
2. **Pagination**: v1 used default `per_page=25`, checking only 1,545/3,070 papers (50.3%). v2 uses `paginate(per_page=200)` for full coverage.
3. **Seed diversity**: v1 used top 10 by citation count (mega-cited, not representative). v2 selects median-cited papers across topic clusters.

## Expected Impact
- Coverage rate may change (v1 reported 48.6% on partial sample)
- Pattern hit rates will likely decrease (fulltext-only vs combined search)
- Results will be more representative of actual fulltext filtering effectiveness

## How to Run
```bash
cd /home/kyuwon/projects/papersift
python scripts/e002_fulltext_coverage.py
```
Results saved to `outputs/e002_v2/`
