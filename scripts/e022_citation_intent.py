"""
e022 Citation Intent — Dead-end Detection via Citation Signals

T0: scite API pilot (50 papers) — expected to fail (no API key)
Fallback: OpenAlex heuristic using cited_by_count + is_retracted + age
Cross-reference with e017 failure signals and e019 deduped limitations
"""

import json
import time
import datetime
import statistics
import re
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE = Path("/home/kyuwon/projects/papersift")
PAPERS_PATH = BASE / "results/virtual-cell-sweep/papers_cleaned.json"
E017_PATH = BASE / "outputs/e017/results.json"
E019_PATH = BASE / "outputs/e019/results.json"
OUT_DIR = BASE / "outputs/e022"
OUT_PATH = OUT_DIR / "results.json"

OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Load inputs
# ---------------------------------------------------------------------------
print("Loading inputs...")
papers = json.loads(PAPERS_PATH.read_text())
e017 = json.loads(E017_PATH.read_text())
e019 = json.loads(E019_PATH.read_text())

# Build doi -> paper map
doi_map = {p["doi"].lower().strip(): p for p in papers if p.get("doi")}
all_dois = list(doi_map.keys())
print(f"  papers: {len(papers)}, unique DOIs: {len(doi_map)}")

# Collect e017 dead-end DOIs (from dead_end_signals across all clusters)
dead_end_dois_e017 = set()
for cid, cl in e017["clusters"].items():
    for sig in cl.get("dead_end_signals", []):
        for doi in sig.get("dois", []):
            dead_end_dois_e017.add(doi.lower().strip())
print(f"  e017 dead-end DOIs: {len(dead_end_dois_e017)}")

# e019 deduped limitations
deduped_limitations = e019.get("deduped_limitations", [])
print(f"  e019 deduped_limitations: {len(deduped_limitations)}")

# Dead-end keywords in limitations
DEAD_END_KEYWORDS = [
    "failed", "unsuccessful", "negative result", "no significant",
    "inconclusive", "not validated", "could not", "unable to",
    "did not", "lack of", "insufficient", "limitation",
    "overestimate", "underestimate", "overfit", "artifact"
]

# ---------------------------------------------------------------------------
# T0: scite API pilot
# ---------------------------------------------------------------------------
print("\nT0: scite API pilot (50 papers)...")
pilot_dois = all_dois[:50]
pilot_coverage = 0.0
pilot_gate = "FAIL"

try:
    sample_doi = pilot_dois[0]
    encoded = urllib.parse.quote(sample_doi, safe="")
    url = f"https://api.scite.ai/citations/{encoded}"
    req = urllib.request.Request(url, headers={"User-Agent": "papersift-e022/1.0"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=5) as resp:
        elapsed = time.time() - t0
        data = json.loads(resp.read())
        # If we got here, check coverage
        n_success = 0
        for doi in pilot_dois:
            enc = urllib.parse.quote(doi, safe="")
            try:
                r = urllib.request.urlopen(
                    urllib.request.Request(
                        f"https://api.scite.ai/citations/{enc}",
                        headers={"User-Agent": "papersift-e022/1.0"}
                    ),
                    timeout=3
                )
                if r.status == 200:
                    n_success += 1
            except Exception:
                pass
        pilot_coverage = n_success / len(pilot_dois)
        if pilot_coverage >= 0.4 and elapsed < 5.0:
            pilot_gate = "PASS"
        print(f"  scite pilot: coverage={pilot_coverage:.1%}, elapsed={elapsed:.2f}s, gate={pilot_gate}")
except urllib.error.HTTPError as e:
    print(f"  scite API HTTP error: {e.code} {e.reason} -> FAIL (expected, no API key)")
except urllib.error.URLError as e:
    print(f"  scite API URL error: {e.reason} -> FAIL")
except Exception as e:
    print(f"  scite API error: {type(e).__name__}: {e} -> FAIL")

pilot_info = {
    "method": "scite_api",
    "n_tested": len(pilot_dois),
    "coverage": pilot_coverage,
    "gate": pilot_gate
}

# ---------------------------------------------------------------------------
# OpenAlex fallback
# ---------------------------------------------------------------------------
print("\nOpenAlex fallback: fetching cited_by_count + is_retracted via API...")
CURRENT_YEAR = 2026
BATCH_SIZE = 50
BASE_URL = "https://api.openalex.org/works"

openalex_data = {}  # doi -> {cited_by_count, is_retracted, year}

# Use existing papers_cleaned data (already has cited_by_count + year)
# But we still query OpenAlex for is_retracted (not in local data)
# Strategy: use local cited_by_count, query OpenAlex for is_retracted in batches

# First, populate from local data
for doi, p in doi_map.items():
    openalex_data[doi] = {
        "cited_by_count": p.get("cited_by_count", 0) or 0,
        "is_retracted": False,  # default; will update from API
        "year": p.get("year", 0) or 0,
    }

# Query OpenAlex in batches for is_retracted
print(f"  Querying OpenAlex for is_retracted on {len(all_dois)} DOIs in batches of {BATCH_SIZE}...")
n_api_success = 0
n_api_fail = 0

for batch_start in range(0, len(all_dois), BATCH_SIZE):
    batch = all_dois[batch_start:batch_start + BATCH_SIZE]
    # pipe-separated DOI filter
    filter_val = "doi:" + "|".join(batch)
    params = urllib.parse.urlencode({
        "filter": filter_val,
        "select": "doi,cited_by_count,is_retracted,publication_year",
        "per_page": BATCH_SIZE,
        "mailto": "papersift@example.com",
    })
    url = f"{BASE_URL}?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "papersift-e022/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            results = data.get("results", [])
            for item in results:
                raw_doi = item.get("doi", "") or ""
                # OpenAlex returns full URL like https://doi.org/10.xxxx
                doi_clean = raw_doi.replace("https://doi.org/", "").lower().strip()
                if doi_clean in openalex_data:
                    openalex_data[doi_clean]["is_retracted"] = item.get("is_retracted", False)
                    # update cited_by_count from API (more current)
                    api_cbc = item.get("cited_by_count", None)
                    if api_cbc is not None:
                        openalex_data[doi_clean]["cited_by_count"] = api_cbc
                    api_year = item.get("publication_year", None)
                    if api_year:
                        openalex_data[doi_clean]["year"] = api_year
                    n_api_success += 1
    except Exception as ex:
        n_api_fail += 1
        if n_api_fail <= 3:
            print(f"    batch {batch_start}: {type(ex).__name__}: {ex}")

    # small pause to be polite
    time.sleep(0.05)

    if (batch_start // BATCH_SIZE) % 10 == 0:
        pct = min(100, int(batch_start / len(all_dois) * 100))
        print(f"  progress: {pct}% ({batch_start}/{len(all_dois)})")

print(f"  API results matched: {n_api_success}, batch failures: {n_api_fail}")

# ---------------------------------------------------------------------------
# Compute stats
# ---------------------------------------------------------------------------
citation_counts = [v["cited_by_count"] for v in openalex_data.values()]
citation_counts_nonzero = [c for c in citation_counts if c > 0]

n_retracted = sum(1 for v in openalex_data.values() if v["is_retracted"])
n_with_citations = sum(1 for c in citation_counts if c > 0)
median_citations = statistics.median(citation_counts) if citation_counts else 0.0

# 25th percentile
sorted_counts = sorted(citation_counts)
p25_idx = max(0, int(len(sorted_counts) * 0.25) - 1)
p25_citations = sorted_counts[p25_idx] if sorted_counts else 0.0

print(f"\nOpenAlex stats:")
print(f"  n_papers_queried: {len(openalex_data)}")
print(f"  n_with_citations: {n_with_citations}")
print(f"  median_citations: {median_citations}")
print(f"  p25_citations: {p25_citations}")
print(f"  n_retracted: {n_retracted}")

# ---------------------------------------------------------------------------
# Dead-end detection heuristic
# ---------------------------------------------------------------------------
print("\nDead-end detection...")

dead_end_set = set()

for doi, v in openalex_data.items():
    age = CURRENT_YEAR - v["year"] if v["year"] > 0 else 0
    is_low_cited = v["cited_by_count"] <= p25_citations
    is_old = age >= 5
    is_retracted = v["is_retracted"]

    if is_retracted or (is_low_cited and is_old):
        dead_end_set.add(doi)

print(f"  heuristic dead-ends (low-cited+old or retracted): {len(dead_end_set)}")

# Overlap with e017 failure-flagged DOIs
failure_overlap = dead_end_set & dead_end_dois_e017
print(f"  overlap with e017 failure-flagged: {len(failure_overlap)}")

total_flagged = len(dead_end_set)
dead_end_rate = len(dead_end_set) / len(openalex_data) if openalex_data else 0.0
print(f"  dead_end_rate: {dead_end_rate:.1%}")

# ---------------------------------------------------------------------------
# e019 integration: dead-end keywords in deduped limitations
# ---------------------------------------------------------------------------
dead_end_kw_found = 0
for lim in deduped_limitations:
    lim_lower = lim.lower()
    if any(kw in lim_lower for kw in DEAD_END_KEYWORDS):
        dead_end_kw_found += 1

print(f"\ne019 integration:")
print(f"  deduped_limitations used: {len(deduped_limitations)}")
print(f"  with dead-end keywords: {dead_end_kw_found}")

# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------
threshold = 0.15  # OpenAlex fallback threshold
verdict = "GO" if dead_end_rate >= threshold else "NO-GO"
verdict_detail = (
    f"dead_end_rate={dead_end_rate:.1%} >= 15% (OpenAlex fallback threshold) -> {verdict}"
)

print(f"\nVerdict: {verdict}")
print(f"  {verdict_detail}")

# ---------------------------------------------------------------------------
# Save results
# ---------------------------------------------------------------------------
results = {
    "experiment": "e022",
    "title": "T5 Citation Intent",
    "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    "pilot": pilot_info,
    "fallback_used": True,
    "method": "openalex_heuristic",
    "openalex_stats": {
        "n_papers_queried": len(openalex_data),
        "n_with_citations": n_with_citations,
        "median_citations": float(median_citations),
        "n_retracted": n_retracted,
        "p25_citations": float(p25_citations),
    },
    "dead_end_detection": {
        "total_flagged": total_flagged,
        "citation_dead_ends": len(dead_end_set),
        "failure_signal_overlap": len(failure_overlap),
        "dead_end_rate": round(dead_end_rate, 4),
    },
    "e019_integration": {
        "deduped_limitations_used": len(deduped_limitations),
        "dead_end_keywords_found": dead_end_kw_found,
    },
    "verdict": verdict,
    "verdict_detail": f"dead_end_rate={dead_end_rate:.1%} >= 15% (OpenAlex fallback threshold)" if verdict == "GO"
                      else f"dead_end_rate={dead_end_rate:.1%} < 15% (OpenAlex fallback threshold)",
}

OUT_PATH.write_text(json.dumps(results, indent=2, ensure_ascii=False))
print(f"\nSaved: {OUT_PATH}")
print("Done.")
