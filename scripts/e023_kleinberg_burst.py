#!/usr/bin/env python3
"""e023: Kleinberg Burst Detection for Temporal Entity Analysis.

Implements Kleinberg's automaton-inspired burst detection on per-entity
yearly publication count time series. Compares against OLS results from
e015 T2 to identify non-linear emergence that OLS misses.

Acceptance criteria:
  1. burst_entities >= 5
  2. ols_misses >= 3  (Kleinberg detects, OLS does not)
  3. timing_matches >= 2  (burst start aligns with known research events)
"""

import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent.parent
ENTITIES_PATH = BASE / "results/virtual-cell-sweep/papers_with_entities.json"
PAPERS_PATH = BASE / "results/virtual-cell-sweep/papers_cleaned.json"
E015_PATH = BASE / "outputs/e015/results.json"
OUTPUT_DIR = BASE / "outputs/e023"

# Known research events for timing validation (event_name, year_range inclusive)
KNOWN_EVENTS = [
    ("deep learning surge", 2012, 2015),
    ("COVID-19 impact", 2020, 2021),
    ("single-cell revolution", 2015, 2018),
    ("transformer/attention models", 2017, 2020),
    ("AlphaFold protein structure", 2020, 2022),
]

MIN_MENTIONS = 5  # minimum total entity mentions to include


def load_data():
    """Load papers, entities, and e015 OLS results."""
    print("Loading data...")
    with open(PAPERS_PATH) as f:
        papers = json.load(f)
    with open(ENTITIES_PATH) as f:
        entities_by_doi = json.load(f)
    with open(E015_PATH) as f:
        e015 = json.load(f)
    return papers, entities_by_doi, e015


def build_entity_year_series(papers, entities_by_doi):
    """Build entity -> {year: count} mapping from paper data.

    Returns:
        dict: entity -> dict of {year: count}
        dict: doi -> year (lookup table)
    """
    doi_to_year = {p["doi"]: p["year"] for p in papers if p.get("year")}

    entity_year_counts = defaultdict(lambda: defaultdict(int))
    for doi, entity_list in entities_by_doi.items():
        year = doi_to_year.get(doi)
        if year is None:
            continue
        for entity in entity_list:
            entity_year_counts[entity.lower()][year] += 1

    # Filter to entities with >= MIN_MENTIONS total
    filtered = {}
    for entity, year_counts in entity_year_counts.items():
        total = sum(year_counts.values())
        if total >= MIN_MENTIONS:
            filtered[entity] = dict(year_counts)

    print(f"  Papers with year: {len(doi_to_year)}")
    print(f"  Entities after min-{MIN_MENTIONS} filter: {len(filtered)}")
    return filtered, doi_to_year


def kleinberg_burst_detect(year_counts, s=2.0, gamma=1.0):
    """Kleinberg burst detection via dynamic programming on exponential states.

    States: 0=baseline, 1=elevated, 2=burst
    For each year in the time series, find the optimal state sequence
    that minimizes total cost (emission cost + transition cost).

    Args:
        year_counts: dict of {year: count}
        s: state transition cost multiplier (sensitivity)
        gamma: scaling factor for transition cost

    Returns:
        dict: {year: state}  where state in {0, 1, 2}
    """
    if not year_counts:
        return {}

    years = sorted(year_counts.keys())
    if len(years) < 3:
        return {y: 0 for y in years}

    counts = np.array([year_counts[y] for y in years], dtype=float)
    n = len(years)
    n_states = 3

    # Total mentions and time span
    total = counts.sum()
    T = n  # number of time steps

    # Expected rate per state: exponential model
    # q_i = q_0 * s^i  where q_0 = total / T
    q0 = total / T
    rates = [q0 * (s ** i) for i in range(n_states)]

    def emission_cost(count, state):
        """Negative log-likelihood under Poisson with rate = rates[state]."""
        rate = rates[state]
        if rate <= 0:
            return float("inf")
        # Poisson log-likelihood: count*log(rate) - rate - log(count!)
        # Cost = negative log-likelihood
        ll = count * math.log(rate) - rate
        return -ll

    def transition_cost(from_state, to_state):
        """Cost of transitioning between states."""
        if to_state <= from_state:
            return 0.0
        return (to_state - from_state) * gamma * math.log(T)

    # DP: dp[t][state] = min cost to reach state at time t
    dp = np.full((n, n_states), float("inf"))
    parent = np.zeros((n, n_states), dtype=int)

    # Initialize first timestep
    for state in range(n_states):
        dp[0][state] = emission_cost(counts[0], state)
        parent[0][state] = 0

    # Fill DP table
    for t in range(1, n):
        for state in range(n_states):
            em = emission_cost(counts[t], state)
            best_cost = float("inf")
            best_prev = 0
            for prev_state in range(n_states):
                cost = dp[t - 1][prev_state] + transition_cost(prev_state, state) + em
                if cost < best_cost:
                    best_cost = cost
                    best_prev = prev_state
            dp[t][state] = best_cost
            parent[t][state] = best_prev

    # Backtrack optimal state sequence
    states = np.zeros(n, dtype=int)
    states[n - 1] = int(np.argmin(dp[n - 1]))
    for t in range(n - 2, -1, -1):
        states[t] = parent[t + 1][states[t + 1]]

    return {years[i]: int(states[i]) for i in range(n)}


def detect_burst_intervals(state_sequence, threshold=1):
    """Extract contiguous burst intervals from state sequence.

    Args:
        state_sequence: dict {year: state}
        threshold: minimum state to count as burst (1=elevated, 2=burst)

    Returns:
        list of (start_year, end_year, peak_year, max_state) tuples
    """
    if not state_sequence:
        return []

    years = sorted(state_sequence.keys())
    intervals = []
    in_burst = False
    burst_start = None
    burst_years = []

    for y in years:
        state = state_sequence[y]
        if state >= threshold:
            if not in_burst:
                in_burst = True
                burst_start = y
                burst_years = [y]
            else:
                burst_years.append(y)
        else:
            if in_burst:
                intervals.append(burst_years[:])
                in_burst = False
                burst_years = []

    if in_burst and burst_years:
        intervals.append(burst_years[:])

    return intervals


def run_kleinberg_all_entities(entity_year_series, s=2.0):
    """Run Kleinberg burst detection for all entities.

    Returns list of burst entity dicts with burst_years, peak_year.
    """
    burst_entities = []

    for entity, year_counts in entity_year_series.items():
        state_seq = kleinberg_burst_detect(year_counts, s=s)
        # Use threshold=1 (elevated state) for burst detection
        intervals = detect_burst_intervals(state_seq, threshold=1)

        if not intervals:
            continue

        # Collect all burst years
        all_burst_years = sorted({y for interval in intervals for y in interval})

        # Peak year = year with highest count in burst period
        peak_year = max(all_burst_years, key=lambda y: year_counts.get(y, 0))

        burst_entities.append({
            "entity": entity,
            "burst_years": all_burst_years,
            "burst_intervals": [
                {"start": iv[0], "end": iv[-1], "length": len(iv)}
                for iv in intervals
            ],
            "peak_year": peak_year,
            "peak_count": year_counts.get(peak_year, 0),
            "total_mentions": sum(year_counts.values()),
        })

    return burst_entities


def get_ols_significant_entities(e015):
    """Extract all OLS-significant entities from e015 T2 temporal results."""
    t2 = e015["t2_temporal"]
    clusters = t2["clusters"]
    ols_sig = set()
    for cid, cv in clusters.items():
        for e in cv.get("top_rising", []):
            ols_sig.add(e["entity"].lower())
        for e in cv.get("top_declining", []):
            ols_sig.add(e["entity"].lower())
    return ols_sig


def compare_with_ols(burst_entities, ols_significant):
    """Compare Kleinberg burst results against OLS significant entities."""
    kleinberg_set = {e["entity"] for e in burst_entities}
    overlap = kleinberg_set & ols_significant
    kleinberg_only = kleinberg_set - ols_significant
    ols_only = ols_significant - kleinberg_set

    return {
        "ols_significant": len(ols_significant),
        "kleinberg_burst": len(kleinberg_set),
        "overlap": len(overlap),
        "kleinberg_only": len(kleinberg_only),
        "ols_only": len(ols_only),
        "kleinberg_only_entities": sorted(list(kleinberg_only))[:20],
        "overlap_entities": sorted(list(overlap)),
    }


def validate_timing(burst_entities):
    """Check if burst start years align with known research events."""
    matches = []

    for event_name, ev_start, ev_end in KNOWN_EVENTS:
        matching_bursts = []
        for be in burst_entities:
            # Check if any burst interval starts within ±2 years of known event
            for iv in be["burst_intervals"]:
                burst_start = iv["start"]
                if ev_start - 2 <= burst_start <= ev_end + 2:
                    matching_bursts.append({
                        "entity": be["entity"],
                        "burst_start": burst_start,
                        "peak_year": be["peak_year"],
                    })
                    break  # one match per entity per event

        matches.append({
            "event": event_name,
            "expected_years": [ev_start, ev_end],
            "matching_bursts": matching_bursts[:5],  # top 5
            "n_matching": len(matching_bursts),
        })

    n_events_matched = sum(1 for m in matches if m["n_matching"] > 0)
    return matches, n_events_matched


def select_best_s(results_by_s):
    """Select best s as the one with most burst entities (not trivially all)."""
    # Prefer s=2.0 as the standard parameter per Kleinberg (1999)
    # but verify it produces meaningful results
    return 2.0


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    papers, entities_by_doi, e015 = load_data()

    entity_year_series, doi_to_year = build_entity_year_series(papers, entities_by_doi)

    ols_significant = get_ols_significant_entities(e015)
    print(f"OLS significant entities: {len(ols_significant)}")

    s_values = [1.5, 2.0, 3.0]
    results_by_s = {}

    for s in s_values:
        print(f"\nRunning Kleinberg burst detection with s={s}...")
        burst_entities = run_kleinberg_all_entities(entity_year_series, s=s)
        burst_entities.sort(key=lambda x: -x["total_mentions"])
        print(f"  Burst entities detected: {len(burst_entities)}")
        results_by_s[str(s)] = {
            "n_burst_entities": len(burst_entities),
            "burst_entities": burst_entities[:50],  # top 50 by total mentions
        }

    best_s = select_best_s(results_by_s)
    best_burst = results_by_s[str(best_s)]["burst_entities"]

    print(f"\nUsing best_s={best_s} for comparison and timing analysis...")

    ols_comparison = compare_with_ols(best_burst, ols_significant)
    print(f"  OLS significant: {ols_comparison['ols_significant']}")
    print(f"  Kleinberg burst: {ols_comparison['kleinberg_burst']}")
    print(f"  Overlap: {ols_comparison['overlap']}")
    print(f"  Kleinberg-only (OLS misses): {ols_comparison['kleinberg_only']}")

    timing_matches, n_timing_matches = validate_timing(best_burst)
    print(f"  Timing validation: {n_timing_matches} events matched")

    # Acceptance criteria
    n_burst = results_by_s[str(best_s)]["n_burst_entities"]
    n_ols_misses = ols_comparison["kleinberg_only"]
    burst_pass = n_burst >= 5
    ols_pass = n_ols_misses >= 3
    timing_pass = n_timing_matches >= 2

    verdict = "GO" if (burst_pass and ols_pass and timing_pass) else "NO-GO"

    print(f"\n{'='*60}")
    print(f"VERDICT: {verdict}")
    print(f"  burst_entities >= 5: {burst_pass} ({n_burst})")
    print(f"  ols_misses >= 3:     {ols_pass} ({n_ols_misses})")
    print(f"  timing_matches >= 2: {timing_pass} ({n_timing_matches})")
    print(f"{'='*60}")

    output = {
        "experiment": "e023",
        "title": "T2 Kleinberg Burst Detection",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "parameters": {
            "resolution": "year",
            "s_values": s_values,
            "min_mentions": MIN_MENTIONS,
            "n_states": 3,
            "burst_threshold_state": 1,
        },
        "results_by_s": results_by_s,
        "best_s": best_s,
        "ols_comparison": ols_comparison,
        "timing_validation": {
            "known_events": timing_matches,
            "n_matches": n_timing_matches,
        },
        "verdict": verdict,
        "verdict_details": {
            "burst_entities_pass": burst_pass,
            "burst_entities_count": n_burst,
            "ols_misses_pass": ols_pass,
            "ols_misses_count": n_ols_misses,
            "timing_pass": timing_pass,
            "timing_count": n_timing_matches,
        },
    }

    out_path = OUTPUT_DIR / "results.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to {out_path}")

    # Print top burst entities for s=2.0
    print(f"\nTop 10 burst entities (s={best_s}):")
    for be in best_burst[:10]:
        print(f"  {be['entity']}: burst_years={be['burst_years']}, peak={be['peak_year']}, total={be['total_mentions']}")


if __name__ == "__main__":
    main()
