#!/usr/bin/env python3
"""
e002 Analysis Summary: Create visualizations and detailed report
"""
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

# Load results
output_dir = Path("/home/kyuwon/projects/papersift/outputs/e002")
with open(output_dir / "fulltext_coverage.json") as f:
    coverage = json.load(f)

with open(output_dir / "filter_patterns.json") as f:
    patterns = json.load(f)

print("=" * 80)
print("E002 ANALYSIS SUMMARY")
print("=" * 80)

# Coverage analysis
print("\n[FINDING] OpenAlex fulltext coverage")
print(f"[STAT:n] n = {coverage['total_checked']}")
print(f"[STAT:rate] coverage_rate = {coverage['coverage_rate']:.3f}")

# Calculate confidence interval
p = coverage['coverage_rate']
n = coverage['total_checked']
se = np.sqrt(p * (1 - p) / n)
ci_lower = p - 1.96 * se
ci_upper = p + 1.96 * se
print(f"[STAT:ci] 95% CI: [{ci_lower:.3f}, {ci_upper:.3f}]")

# API limitation
check_rate = coverage['total_checked'] / coverage['total_papers']
print(f"\n[LIMITATION] API returned only {coverage['total_checked']}/{coverage['total_papers']} papers ({100*check_rate:.1f}%)")
print(f"[LIMITATION] Missing {coverage['total_papers'] - coverage['total_checked']} papers may be inaccessible via API")

print("\n[FINDING] Filter pattern effectiveness ranked by avg hit rate")
stats = patterns['pattern_stats']
ranked = sorted(stats.items(), key=lambda x: x[1]['avg_hit_rate'], reverse=True)
for rank, (name, data) in enumerate(ranked, 1):
    print(f"  {rank}. {name:20s} {data['avg_hit_rate']:>6.1%} (n={data['n_seeds']})")

# Key comparisons
print("\n[FINDING] Method proposal vs SOTA patterns")
method_rate = stats['method_proposal']['avg_hit_rate']
sota_narrow_rate = stats['sota_narrow']['avg_hit_rate']
sota_broad_rate = stats['sota_broad']['avg_hit_rate']
print(f"[STAT:effect_size] method_proposal is {method_rate/sota_narrow_rate:.1f}x more prevalent than sota_narrow")
print(f"[STAT:effect_size] method_proposal is {method_rate/sota_broad_rate:.1f}x more prevalent than sota_broad")

print("\n[FINDING] Combined pattern underperforms individual patterns")
combined_rate = stats['combined']['avg_hit_rate']
print(f"[STAT:rate] combined = {combined_rate:.3f} vs method_proposal = {method_rate:.3f}")
print(f"[LIMITATION] OR query may have different semantics than expected in fulltext search")

# Create visualizations
print("\n" + "=" * 80)
print("Creating visualizations...")
print("=" * 80)

fig, axes = plt.subplots(1, 2, figsize=(14, 5))

# Panel A: Coverage breakdown
ax = axes[0]
labels = ['Fulltext Available', 'No Fulltext', 'Not Checked (API)']
sizes = [
    coverage['fulltext_available'],
    coverage['total_checked'] - coverage['fulltext_available'],
    coverage['total_papers'] - coverage['total_checked']
]
colors = ['#2ecc71', '#e74c3c', '#95a5a6']
explode = (0.05, 0, 0)

wedges, texts, autotexts = ax.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%',
                                    startangle=90, explode=explode)
for autotext in autotexts:
    autotext.set_color('white')
    autotext.set_fontweight('bold')
    autotext.set_fontsize(10)

ax.set_title('A. OpenAlex Fulltext Coverage (n=3,070)', fontsize=12, fontweight='bold', pad=20)

# Panel B: Pattern hit rates
ax = axes[1]
pattern_names = [name.replace('_', '\n') for name, _ in ranked]
hit_rates = [data['avg_hit_rate'] * 100 for _, data in ranked]
colors_bar = ['#3498db', '#2ecc71', '#f39c12', '#e74c3c', '#9b59b6']

bars = ax.barh(pattern_names, hit_rates, color=colors_bar)
ax.set_xlabel('Average Hit Rate (%)', fontsize=11, fontweight='bold')
ax.set_title('B. Filter Pattern Effectiveness (n=10 seeds)', fontsize=12, fontweight='bold', pad=20)
ax.grid(axis='x', alpha=0.3, linestyle='--')

# Add value labels
for i, (bar, rate) in enumerate(zip(bars, hit_rates)):
    ax.text(rate + 1, i, f'{rate:.1f}%', va='center', fontsize=9, fontweight='bold')

plt.tight_layout()
viz_path = output_dir / "e002_summary.png"
plt.savefig(viz_path, dpi=300, bbox_inches='tight')
plt.close()
print(f"[OUTPUT] Visualization saved to {viz_path}")

# Create detailed seed analysis visualization
fig, ax = plt.subplots(figsize=(12, 8))

detailed = patterns['detailed_results']
seeds = detailed['method_proposal']  # Use method_proposal as baseline

# Get all patterns for each seed
seed_titles = [s['seed_title'][:40] + '...' if len(s['seed_title']) > 40 else s['seed_title']
               for s in seeds]
y_pos = np.arange(len(seed_titles))

# Bar positions
bar_width = 0.15
positions = [y_pos + i*bar_width for i in range(-2, 3)]

# Plot each pattern
pattern_order = ['improvement', 'method_proposal', 'combined', 'sota_narrow', 'sota_broad']
colors_detailed = ['#2ecc71', '#3498db', '#9b59b6', '#e74c3c', '#f39c12']

for idx, (pattern_name, color) in enumerate(zip(pattern_order, colors_detailed)):
    rates = [r['hit_rate'] * 100 for r in detailed[pattern_name]]
    ax.barh(positions[idx], rates, bar_width, label=pattern_name.replace('_', ' ').title(),
            color=color, alpha=0.8)

ax.set_yticks(y_pos)
ax.set_yticklabels(seed_titles, fontsize=9)
ax.set_xlabel('Hit Rate (%)', fontsize=11, fontweight='bold')
ax.set_title('Filter Pattern Performance Across Top 10 Cited Papers',
             fontsize=12, fontweight='bold', pad=20)
ax.legend(loc='lower right', fontsize=9)
ax.grid(axis='x', alpha=0.3, linestyle='--')

plt.tight_layout()
detail_path = output_dir / "e002_detailed_patterns.png"
plt.savefig(detail_path, dpi=300, bbox_inches='tight')
plt.close()
print(f"[OUTPUT] Detailed pattern analysis saved to {detail_path}")

# Generate markdown report
print("\n" + "=" * 80)
print("Generating markdown report...")
print("=" * 80)

report = f"""# E002: OpenAlex Fulltext Coverage & Filter Pattern Analysis

**Date**: 2026-02-26
**Dataset**: Virtual Cell Sweep (3,070 papers)
**Objective**: Measure OpenAlex fulltext indexing coverage and SOTA text filtering pattern effectiveness

---

## Executive Summary

### Key Findings

1. **Fulltext Coverage: 48.6% (GO)**
   - 751 out of 1,545 checked papers have fulltext indexed
   - 95% CI: [{ci_lower:.1%}, {ci_upper:.1%}]
   - **Decision: GO** (threshold: 30%)

2. **Best Filter Pattern: "improvement" (29.7%)**
   - Outperforms all other patterns tested
   - 3.8x more effective than SOTA-narrow patterns

3. **Method Proposal vs SOTA**
   - Method proposal: 26.8% avg hit rate
   - SOTA narrow: 7.8% avg hit rate
   - SOTA broad: 7.3% avg hit rate
   - **Method proposal is {method_rate/sota_narrow_rate:.1f}x more prevalent**

---

## Detailed Results

### 1. Fulltext Indexing Coverage

| Metric | Value |
|--------|-------|
| Total papers in dataset | {coverage['total_papers']:,} |
| Papers checked via API | {coverage['total_checked']:,} ({100*check_rate:.1f}%) |
| Fulltext available | {coverage['fulltext_available']:,} |
| **Coverage rate** | **{100*coverage['coverage_rate']:.1f}%** |
| 95% Confidence Interval | [{100*ci_lower:.1f}%, {100*ci_upper:.1f}%] |

**Go/No-Go**: {coverage['go_no_go']} ✓

### 2. Filter Pattern Performance

Ranked by average hit rate across 10 seed papers (total 1.27M citing papers):

| Rank | Pattern | Avg Hit Rate | Total Hits | Effect Size |
|------|---------|--------------|------------|-------------|
"""

for rank, (name, data) in enumerate(ranked, 1):
    report += f"| {rank} | {name.replace('_', ' ').title()} | {data['avg_hit_rate']:.1%} | {data['total_hits']:,} | "
    if name == 'method_proposal':
        report += f"{data['avg_hit_rate']/sota_narrow_rate:.1f}x SOTA-narrow |\n"
    elif name == 'improvement':
        report += f"{data['avg_hit_rate']/sota_narrow_rate:.1f}x SOTA-narrow |\n"
    else:
        report += "— |\n"

report += f"""
### 3. Seed Papers (Top 10 by Citations)

| Paper | Citations | Best Pattern | Hit Rate |
|-------|-----------|--------------|----------|
"""

for seed in seeds:
    # Find best pattern for this seed
    best_rate = 0
    best_pattern = ""
    for pattern_name in pattern_order:
        for result in detailed[pattern_name]:
            if result['seed_doi'] == seed['seed_doi']:
                if result['hit_rate'] > best_rate:
                    best_rate = result['hit_rate']
                    best_pattern = pattern_name

    title_short = seed['seed_title'][:50] + '...' if len(seed['seed_title']) > 50 else seed['seed_title']
    report += f"| {title_short} | {seed['total_citing']:,} | {best_pattern.replace('_', ' ')} | {best_rate:.1%} |\n"

report += """
---

## Visualizations

### Figure 1: Coverage and Pattern Effectiveness
![E002 Summary](e002_summary.png)

**Panel A**: Fulltext coverage breakdown showing 48.6% of accessible papers have indexed fulltext.

**Panel B**: Filter pattern comparison ranked by effectiveness. "Improvement" and "method proposal" patterns significantly outperform SOTA-focused patterns.

### Figure 2: Pattern Performance by Seed Paper
![E002 Detailed Patterns](e002_detailed_patterns.png)

Pattern hit rates vary significantly across seed papers, with ML/CV papers (ResNet, LSTM, Random Forest) showing highest SOTA-narrow rates (13-25%) while methodology papers show lower rates (1-4%).

---

## Key Insights

### Finding 1: Fulltext Coverage is Adequate for Tier-1 Strategy
- **Evidence**: 48.6% coverage (95% CI: [46.1%, 51.1%])
- **Interpretation**: Nearly half of papers have searchable fulltext, sufficient for filtering strategies
- **Caveat**: API returned only 50.3% of dataset; missing papers may have different coverage rates

### Finding 2: Method Proposal Patterns Outperform SOTA Patterns
- **Evidence**: 26.8% vs 7.8% avg hit rate (3.4x difference)
- **Interpretation**: Papers more commonly describe new methods than claim SOTA performance
- **Implication**: Use method-focused filters for broader recall; SOTA filters for high-precision

### Finding 3: "Improvement" Pattern Shows Highest Recall
- **Evidence**: 29.7% avg hit rate across all seed papers
- **Interpretation**: "improves/extends/enhances/advances" captures incremental contributions
- **Recommendation**: Consider "improvement" as primary filter for broad method discovery

### Finding 4: Combined Patterns Underperform
- **Evidence**: Combined pattern (9.8%) < method_proposal (26.8%)
- **Interpretation**: Likely due to OpenAlex OR query semantics in fulltext search
- **Limitation**: May require investigation of query processing behavior

### Finding 5: Domain-Specific Variation
- **Evidence**: ML/CV papers show 13-25% SOTA-narrow rate vs 1-4% in methodology papers
- **Interpretation**: SOTA claims are field-dependent; ML/DL papers emphasize benchmarking
- **Implication**: Pattern selection should consider target domain characteristics

---

## Limitations

1. **API Coverage Gap**: Only 50.3% of papers returned by API; missing papers may bias coverage estimates
2. **Seed Paper Bias**: Top 10 cited papers may not represent typical papers in dataset
3. **Pattern Specificity**: Tested patterns are English-centric and may miss non-English fulltext
4. **Citation Context**: Hit rates based on total citing papers; does not assess relevance quality
5. **Query Semantics**: OpenAlex fulltext search behavior for OR queries requires further investigation

---

## Recommendations for Tier-1 Strategy

### Go Decision: Proceed with Fulltext Filtering
Coverage of 48.6% exceeds 30% threshold. Fulltext search is viable for Tier-1.

### Recommended Filter Patterns (Ranked):
1. **"improvement" pattern** (29.7% recall) — Broadest coverage of methodological advances
2. **"method_proposal" pattern** (26.8% recall) — Strong for novel method discovery
3. **"sota_narrow" pattern** (7.8% recall) — High precision for benchmark papers (ML/DL domains)
4. **Avoid "combined" pattern** — Underperforms individual patterns due to query semantics

### Implementation Strategy:
- **Phase 1**: Use "improvement" OR "method_proposal" for high recall
- **Phase 2**: Apply "sota_narrow" as secondary filter for benchmark-focused papers
- **Domain-aware**: Adjust pattern weights based on field (higher SOTA weight for ML/CV)

---

## Data Availability

- **Coverage Results**: `outputs/e002/fulltext_coverage.json`
- **Pattern Analysis**: `outputs/e002/filter_patterns.json`
- **Execution Log**: `outputs/e002/execution.log`
- **Visualizations**: `outputs/e002/e002_summary.png`, `outputs/e002/e002_detailed_patterns.png`

---

**Report Generated**: {output_dir / 'e002_report.md'}
"""

report_path = output_dir / "e002_report.md"
with open(report_path, 'w') as f:
    f.write(report)

print(f"[OUTPUT] Report saved to {report_path}")
print("\n" + "=" * 80)
print("ANALYSIS COMPLETE")
print("=" * 80)
print(f"\nAll outputs saved to: {output_dir}")
print(f"- fulltext_coverage.json")
print(f"- filter_patterns.json")
print(f"- execution.log")
print(f"- e002_summary.png")
print(f"- e002_detailed_patterns.png")
print(f"- e002_report.md")
