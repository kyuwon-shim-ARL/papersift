#!/usr/bin/env python3
"""Generate landscape report from Virtual Cell sweep analysis data.

Produces:
- Layer 2: Korean-language markdown report (landscape-report.md)
- Layer 3: Standalone interactive HTML dashboard (landscape-dashboard.html)

Usage:
    python scripts/generate_landscape_report.py --all
    python scripts/generate_landscape_report.py --markdown
    python scripts/generate_landscape_report.py --html
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Method name mapping: method_flows.json (abbreviated) <-> trend_analysis.json (full)
# ---------------------------------------------------------------------------
ABBREV_TO_FULL = {
    "ABM": "Agent-based model",
    "ML/DL": "Machine learning / Deep learning",
    "docking/VS": "Docking / Virtual screening",
    "FEM": "Finite element / FEM",
    "GRN": "Gene regulatory network",
    "PK/PBPK": "Pharmacokinetic / PK",
    "stochastic": "Stochastic simulation",
    "multiscale": "Multiscale modeling",
    "whole-cell": "Whole-cell model",
    "systems biology": "Systems biology",
    "molecular dynamics": "Molecular dynamics",
    "FBA": "FBA / Flux balance",
    "Boolean": "Boolean network",
    "QSAR": "QSAR / QSPR",
    "constraint-based": "Constraint-based",
    "ODE": "ODE",
    "PDE": "PDE",
    "Bayesian": "Bayesian",
    "Markov": "Markov",
    "Monte Carlo": "Monte Carlo",
    "single-cell/scRNA": "single-cell/scRNA",
    "digital twin": "digital twin",
}
FULL_TO_ABBREV = {v: k for k, v in ABBREV_TO_FULL.items()}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_data(input_dir: Path) -> dict:
    """Load all analysis JSON files and build indices."""
    def _load(name: str) -> dict | list:
        path = input_dir / name
        if not path.exists():
            print(f"ERROR: {path} not found", file=sys.stderr)
            sys.exit(1)
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    landscape = _load("landscape_map.json")
    flows = _load("method_flows.json")
    trends = _load("trend_analysis.json")
    hypotheses = _load("hypotheses.json")
    papers = _load("papers_enriched.json")

    doi_index = {}
    for p in papers:
        if p.get("doi"):
            doi_index[p["doi"]] = p

    return {
        "landscape": landscape,
        "flows": flows,
        "trends": trends,
        "hypotheses": hypotheses,
        "papers": papers,
        "doi_index": doi_index,
    }


def abbrev(full_name: str) -> str:
    """Convert full method name to abbreviated display name."""
    return FULL_TO_ABBREV.get(full_name, full_name)


def full_name(abbrev_name: str) -> str:
    """Convert abbreviated method name to full name for trend lookups."""
    return ABBREV_TO_FULL.get(abbrev_name, abbrev_name)


# ---------------------------------------------------------------------------
# Layer 2: Markdown report
# ---------------------------------------------------------------------------

def _generate_synthesis(data: dict) -> list[str]:
    """Generate data-driven synthesis insights (not hardcoded).

    Analyzes the landscape data to produce 3-5 key insights about:
    - Cross-cutting methods
    - Emerging trends
    - Method convergence/hybridization
    - Domain-specific patterns

    Returns:
        List of insight strings (markdown formatted)
    """
    insights = []

    landscape = data.get("landscape", {})
    flows = data.get("flows", {})
    trends = data.get("trends", {})
    hyp = data.get("hypotheses", {})

    domains = landscape.get("level_0", {}).get("domains", {})
    method_flows = flows.get("method_flows", {})
    emerging = trends.get("task3_emerging_declining_methods", {})
    gaps = hyp.get("gap_analysis", {}).get("white_spaces_top20", [])

    # 1. Find most cross-cutting method (appears in most domains)
    method_domain_count = {}
    for did, dom in domains.items():
        method_dist = dom.get("method_distribution", {})
        for method, count in method_dist.items():
            if count > 0:
                method_domain_count[method] = method_domain_count.get(method, 0) + 1

    if method_domain_count:
        top_method = max(method_domain_count, key=method_domain_count.get)
        top_count = method_domain_count[top_method]
        n_domains = len(domains)
        insights.append(
            f"1. **{abbrev(top_method)}의 범분야 침투**: {abbrev(top_method)}은(는) "
            f"{n_domains}개 도메인 중 {top_count}개에서 활발히 채택되고 있는 "
            f"가장 범분야적 방법론이다."
        )

    # 2. Find emerging trends (fastest growing methods)
    emerging_methods = [
        (m, info) for m, info in emerging.items()
        if isinstance(info, dict) and info.get("trend") == "emerging"
    ]
    if emerging_methods:
        emerging_methods.sort(key=lambda x: x[1].get("ratio", 0), reverse=True)
        top_emerging = emerging_methods[:3]
        top_em_names = [abbrev(m) for m, _ in top_emerging]
        top_em_first = top_emerging[0]
        insights.append(
            f"2. **신흥 방법론 부상**: {', '.join(top_em_names)}이(가) 급부상하고 있으며, "
            f"특히 {abbrev(top_em_first[0])}은(는) 2020년 이후 "
            f"{top_em_first[1].get('ratio', 0):.1f}배 성장세를 보인다."
        )

    # 3. Find method combinations/convergence patterns
    convergent_methods = flows.get("summary_stats", {}).get("convergent_methods", [])
    if convergent_methods:
        # Get top 3 convergent methods with their distribution spread
        conv_details = []
        for m_info in convergent_methods[:5]:
            m_name = m_info if isinstance(m_info, str) else m_info.get("method", "")
            flow = method_flows.get(m_name, {})
            dist = flow.get("cluster_distribution", {})
            n_clusters = len(dist)
            if n_clusters >= 3:
                conv_details.append((m_name, n_clusters))

        if conv_details:
            conv_details.sort(key=lambda x: x[1], reverse=True)
            top_conv = conv_details[:3]
            combo_text = ", ".join(f"{abbrev(m)}({n}개 클러스터)" for m, n in top_conv)
            insights.append(
                f"3. **방법론 하이브리드화**: 방법론 간 수렴이 진행 중이며, "
                f"{combo_text} 등이 도메인 경계를 넘어 확산하고 있다. "
                "이는 단일 접근법으로 해결 불가능한 복잡한 연구 문제의 증가를 시사한다."
            )

    # 4. Identify major research opportunity from gaps
    if gaps:
        top_gap = gaps[0]
        insights.append(
            f"4. **최대 연구 기회**: {top_gap.get('problem', '?')}에 "
            f"{top_gap.get('method', '?')}을(를) 적용하는 연구가 부재하며, "
            f"기회 점수 {top_gap.get('opportunity_score', 0):,}로 가장 높은 잠재적 영향력을 제공한다."
        )

    # 5. Domain specialization vs convergence balance
    divergent_methods = flows.get("summary_stats", {}).get("divergent_methods", [])
    stable_methods = flows.get("summary_stats", {}).get("stable_methods", [])
    if convergent_methods and divergent_methods:
        insights.append(
            f"5. **수렴-발산 균형**: {len(convergent_methods)}개 방법론은 도메인 간 수렴 패턴을, "
            f"{len(divergent_methods)}개 방법론은 특정 도메인 고착 패턴을 보이며, "
            f"방법론 생태계가 범용성과 특수화의 균형을 유지하고 있다."
        )

    return insights


def generate_markdown(data: dict, output_dir: Path) -> Path:
    """Generate Korean-language markdown report."""
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "landscape-report.md"

    landscape = data["landscape"]
    flows = data["flows"]
    trends = data["trends"]
    hyp = data["hypotheses"]
    doi_index = data["doi_index"]

    domains = landscape["level_0"]["domains"]
    total_papers = landscape["metadata"]["total_biology_papers"]
    total_methods = flows["summary_stats"]["total_methods_analyzed"]

    lines: list[str] = []

    def w(s: str = "") -> None:
        lines.append(s)

    # --- Executive Summary ---
    w("# Virtual Cell 연구 지형도")
    w()
    w(f"> **{total_papers:,}**편의 생물학 논문 | **{len(domains)}**개 연구 도메인 | "
      f"**{total_methods}**개 방법론 | **{len(hyp['hypotheses'])}**개 가설")
    w()
    w(f"*생성일: {datetime.now().strftime('%Y-%m-%d')} | "
      f"데이터: results/virtual-cell-sweep/*")
    w()
    w("---")
    w()
    w("## 1. 핵심 발견 (Executive Summary)")
    w()

    # Key finding 1: largest domain
    sorted_domains = sorted(domains.items(), key=lambda x: x[1]["paper_count"], reverse=True)
    d_top = sorted_domains[0]
    w(f"1. **최대 연구 도메인**: {d_top[1]['name']} ({d_top[1]['paper_count']}편, "
      f"{d_top[1]['paper_count']/total_papers*100:.0f}%)")

    # Key finding 2: fastest growing method
    # task3 is a dict of method_name -> {ratio, trend, ...}
    emerging = trends.get("task3_emerging_declining_methods", {})
    emerging_methods = [
        (m, info) for m, info in emerging.items()
        if isinstance(info, dict) and info.get("trend") == "emerging"
    ]
    if emerging_methods:
        # Sort by ratio (growth multiplier)
        emerging_methods.sort(key=lambda x: x[1].get("ratio", 0), reverse=True)
        top_em_name, top_em_info = emerging_methods[0]
        w(f"2. **급부상 방법론**: {abbrev(top_em_name)} "
          f"(성장률 {top_em_info.get('ratio', 0):.1f}x, "
          f"post-2020 {top_em_info.get('post2020_count', 0)}편)")
    else:
        w("2. **급부상 방법론**: (데이터 없음)")

    # Key finding 3: biggest research gap
    gaps = hyp.get("gap_analysis", {}).get("white_spaces_top20", [])
    if gaps:
        g = gaps[0]
        w(f"3. **최대 연구 공백**: {g['problem']} x {g['method']} "
          f"(기회 점수: {g['opportunity_score']:,})")

    # Key finding 4: convergence trend
    conv = flows["summary_stats"]
    w(f"4. **방법론 수렴**: {len(conv['convergent_methods'])}개 방법론이 도메인 간 수렴 추세")

    # Key finding 5: top hypothesis
    high_hyps = [h for h in hyp["hypotheses"] if h["confidence"] == "High"]
    if high_hyps:
        w(f"5. **최우선 가설**: {high_hyps[0]['id']} — {high_hyps[0]['title']}")

    w()
    w("---")
    w()

    # --- Hierarchy Tree ---
    w("## 2. 연구 계층 구조 (3-Level Hierarchy)")
    w()
    w("```")
    w(f"Virtual Cell Research ({total_papers:,} papers)")

    for i, (did, dom) in enumerate(sorted_domains):
        is_last_domain = (i == len(sorted_domains) - 1)
        prefix = "└── " if is_last_domain else "├── "
        cont = "    " if is_last_domain else "│   "

        trend_arrow = {"growing": "▲", "declining": "▼", "stable": "—"}.get(
            dom.get("temporal_trend", "stable"), "—")

        w(f"{prefix}{did}: {dom['name']} ({dom['paper_count']}편) {trend_arrow}")

        # Sort problem categories by paper count
        pcs = sorted(dom["problem_categories"].items(),
                      key=lambda x: x[1]["paper_count"], reverse=True)

        for j, (pname, pdata) in enumerate(pcs[:5]):  # top 5 per domain
            is_last_pc = (j == min(4, len(pcs) - 1))
            pc_prefix = f"{cont}└── " if is_last_pc else f"{cont}├── "
            pc_cont = f"{cont}    " if is_last_pc else f"{cont}│   "

            pc_trend = {"growing": "▲", "declining": "▼", "stable": "—"}.get(
                pdata.get("temporal_trend", "stable"), "—")
            w(f"{pc_prefix}{pname} ({pdata['paper_count']}편) {pc_trend}")

            # Top 3 methods
            methods = pdata.get("methods", {})
            sorted_methods = sorted(
                [(m, md["paper_count"]) for m, md in methods.items() if m != "Unspecified"],
                key=lambda x: x[1], reverse=True
            )[:3]
            for k, (mname, mcount) in enumerate(sorted_methods):
                is_last_m = (k == len(sorted_methods) - 1)
                m_prefix = f"{pc_cont}└── " if is_last_m else f"{pc_cont}├── "
                w(f"{m_prefix}{mname}: {mcount}편")

        if len(pcs) > 5:
            w(f"{cont}    ... +{len(pcs)-5} more categories")

    w("```")
    w()
    w("### 주요 연구 영역 해석")
    w()
    w("| 도메인 | 핵심 영역 | 주요 방법론 | 트렌드 | So What? |")
    w("|--------|----------|------------|--------|---------|")

    # For each domain, pick top 2 problem categories and generate interpretation
    for did, dom in sorted_domains[:5]:  # top 5 domains
        pcs = sorted(dom["problem_categories"].items(),
                      key=lambda x: x[1]["paper_count"], reverse=True)

        for pname, pdata in pcs[:2]:  # top 2 per domain
            # Get trend
            trend = pdata.get("temporal_trend", "stable")
            trend_kr = {"growing": "확대 중", "declining": "축소 중", "stable": "안정"}.get(trend, "안정")

            # Get dominant method
            methods = pdata.get("methods", {})
            sorted_methods = sorted(
                [(m, md["paper_count"]) for m, md in methods.items() if m != "Unspecified"],
                key=lambda x: x[1], reverse=True
            )
            dominant_method = sorted_methods[0][0] if sorted_methods else "미분류"

            # Build "So What?" interpretation
            if trend == "growing" and "ML/DL" in dominant_method or "Machine learning" in dominant_method:
                so_what = "ML/DL 기반 접근 확대 중"
            elif trend == "declining" and "ABM" in dominant_method or "Agent-based" in dominant_method:
                so_what = "전통적 ABM 방식 퇴조"
            elif trend == "stable" and ("docking" in dominant_method.lower() or "screening" in dominant_method.lower()):
                so_what = "Docking/VS 기반 연구 지속"
            elif trend == "growing":
                so_what = f"{dominant_method} 중심 성장세"
            elif trend == "declining":
                so_what = f"{dominant_method} 기반 연구 감소"
            else:
                so_what = f"{dominant_method} 기반 안정적 연구"

            w(f"| {dom['name'][:15]} | {pname[:20]} | {dominant_method[:15]} | {trend_kr} | {so_what} |")

    w()
    w("---")
    w()

    # --- Domain Cards ---
    w("## 3. 도메인별 프로파일")
    w()

    for did, dom in sorted_domains:
        w(f"### {did}: {dom['name']} ({dom['paper_count']}편)")
        w()

        # Problem list
        pcs = sorted(dom["problem_categories"].items(),
                      key=lambda x: x[1]["paper_count"], reverse=True)
        top_probs = [(name, pd["paper_count"]) for name, pd in pcs[:5]]
        w("**핵심 문제 영역**: " + ", ".join(
            f"{name} ({count})" for name, count in top_probs))
        w()

        # Method distribution
        md = dom.get("method_distribution", {})
        sorted_methods = sorted(md.items(), key=lambda x: x[1], reverse=True)[:5]
        w("**주요 방법론**: " + ", ".join(
            f"{abbrev(m)} ({c})" for m, c in sorted_methods))
        w()

        # Trend
        trend_arrow = {"growing": "▲ 성장", "declining": "▼ 하락", "stable": "— 안정"}.get(
            dom.get("temporal_trend", "stable"), "— 안정")
        w(f"**트렌드**: {trend_arrow}")
        w()

        # Top cited papers from this domain (deduplicated)
        top_papers = []
        seen_dois: set[str] = set()
        for pname, pdata in pcs[:5]:
            for tp in pdata.get("top_papers", [])[:2]:
                doi = tp.get("doi", "")
                if doi and doi in doi_index and doi not in seen_dois:
                    top_papers.append(tp)
                    seen_dois.add(doi)
        top_papers.sort(key=lambda x: x.get("cited_by_count", 0), reverse=True)

        if top_papers[:3]:
            w("**핵심 논문**:")
            for tp in top_papers[:3]:
                title = tp.get("title", "")[:80]
                w(f"- {title} ({tp.get('year', '?')}, "
                  f"{tp.get('cited_by_count', 0):,} citations) "
                  f"[{tp['doi']}]")
            w()

        # Convergence/divergence signals
        conv_sigs = dom.get("convergence_signals", [])
        if conv_sigs:
            sig = conv_sigs[0]
            w(f"**수렴 신호**: {sig.get('method', '?')} "
              f"(home: {sig.get('home_domain_name', '?')}, "
              f"이 도메인에서 {sig.get('papers_here', 0)}편)")

        div_sigs = dom.get("divergence_signals", [])
        if div_sigs:
            sig = div_sigs[0]
            w(f"**고유 방법론**: {sig.get('method', '?')} "
              f"({sig.get('papers', 0)}편, 이 도메인에서만 활발)")

        w()
        w("---")
        w()

    # --- Method Flow Diagram ---
    w("## 4. 방법론 수렴/발산 지도")
    w()

    convergent = flows["summary_stats"]["convergent_methods"]
    divergent = flows["summary_stats"]["divergent_methods"]
    stable = flows["summary_stats"]["stable_methods"]

    w("### 수렴 방법론 (여러 도메인으로 확산)")
    w()
    w("| 방법론 | Home | 분포 | 트렌드 |")
    w("|--------|------|------|--------|")

    for m_info in convergent[:7]:
        m_name = m_info if isinstance(m_info, str) else m_info.get("method", "?")
        flow = flows["method_flows"].get(m_name, {})
        home = flow.get("home_cluster", "?")
        dist = flow.get("cluster_distribution", {})
        sorted_dist = sorted(dist.items(), key=lambda x: x[1], reverse=True)[:3]
        dist_str = " → ".join(f"{c}({n})" for c, n in sorted_dist)
        direction = flow.get("flow_direction", "?")
        w(f"| {m_name} | {home} | {dist_str} | {direction} |")

    w()
    w("### 발산 방법론 (특정 도메인에 고착)")
    w()
    w("| 방법론 | Home | 집중도 | 트렌드 |")
    w("|--------|------|--------|--------|")

    for m_info in divergent[:5]:
        m_name = m_info if isinstance(m_info, str) else m_info.get("method", "?")
        flow = flows["method_flows"].get(m_name, {})
        home = flow.get("home_cluster", "?")
        dist = flow.get("cluster_distribution", {})
        total = sum(dist.values())
        # home is a string like "C5", dist keys are "C0", "C1", etc.
        home_count = dist.get(home, 0)
        pct = (home_count / total * 100) if total > 0 else 0
        direction = flow.get("flow_direction", "?")
        w(f"| {m_name} | {home} | {pct:.0f}% home ({home_count}/{total}) | {direction} |")

    w()
    w("### 안정 방법론 (균등 분포)")
    w()
    stable_names = [m if isinstance(m, str) else m.get("method", "?") for m in stable]
    w(", ".join(stable_names))

    w()
    w("---")
    w()

    # --- Research Gaps ---
    w("## 5. 연구 공백 & 기회")
    w()
    w("| 순위 | 문제 영역 | 부재 방법론 | 기회 점수 | 의미 |")
    w("|------|-----------|------------|-----------|------|")

    for i, g in enumerate(gaps[:10], 1):
        problem = g.get("problem", "?")
        method = g.get("method", "?")
        score = g.get("opportunity_score", 0)
        p_papers = g.get("problem_papers", 0)
        m_papers = g.get("method_papers", 0)
        meaning = f"{problem}({p_papers}편)에 {method}({m_papers}편)이 거의 미적용"
        w(f"| {i} | {problem} | {method} | {score:,} | {meaning} |")

    w()
    w("---")
    w()

    # --- Hypotheses ---
    w("## 6. 연구 가설 & 향후 방향")
    w()

    all_hyps = hyp["hypotheses"]
    high = [h for h in all_hyps if h["confidence"] == "High"]
    medium = sorted(
        [h for h in all_hyps if h["confidence"] == "Medium"],
        key=lambda h: len(h.get("supporting_dois", [])),
        reverse=True,
    )
    selected = high + medium[:5 - len(high)]

    for h in selected:
        conf_badge = {"High": "🔴 High", "Medium": "🟡 Medium", "Low": "⚪ Low"}.get(
            h["confidence"], h["confidence"])
        w(f"### {h['id']}: {h['title']} ({conf_badge})")
        w()
        w(f"**가설**: {h.get('hypothesis', '')}")
        w()

        evidence = h.get("evidence", {})
        if isinstance(evidence, dict):
            support = evidence.get("support", "")
            if support:
                w(f"**근거**: {support}")
        elif isinstance(evidence, str):
            w(f"**근거**: {evidence}")
        w()

        impact = h.get("impact", "")
        if impact:
            w(f"**영향**: {impact}")
            w()

        dois = h.get("supporting_dois", [])
        if dois:
            w("**관련 논문**:")
            for doi in dois[:3]:
                paper = doi_index.get(doi, {})
                title = paper.get("title", doi)[:70]
                year = paper.get("year", "?")
                w(f"- {title} ({year}) [{doi}]")
            w()

        # Next step recommendation based on classification
        classification = h.get("classification", {})
        if isinstance(classification, dict):
            bridge = classification.get("bridge_type", "")
            if bridge:
                next_step = f"**다음 단계**: {bridge} 방향의 후속 연구 설계 권장"
            else:
                next_step = "**다음 단계**: 파일럿 연구를 통한 가설 검증 권장"
        else:
            next_step = "**다음 단계**: 파일럿 연구를 통한 가설 검증 권장"
        w(next_step)
        w()

        w()

    # --- Problem x Method Matrix ---
    w("---")
    w()
    w("## 7. 문제 x 방법론 매트릭스")
    w()

    matrix = trends.get("task5_problem_method_matrix", {})
    if matrix:
        # Find top 10 methods by total count
        method_totals: dict[str, int] = {}
        for p, methods in matrix.items():
            for m, c in methods.items():
                method_totals[m] = method_totals.get(m, 0) + c
        top_methods = [m for m, _ in sorted(method_totals.items(),
                                             key=lambda x: x[1], reverse=True)[:10]]

        # Short labels for problems
        prob_labels = {}
        for p in matrix:
            if ": " in p:
                short = p.split(": ", 1)[1]
            else:
                short = p
            prob_labels[p] = short[:25]

        # Header
        header = "| 문제 \\ 방법 | " + " | ".join(abbrev(m)[:12] for m in top_methods) + " |"
        sep = "|" + "---|" * (len(top_methods) + 1)
        w(header)
        w(sep)

        for p in matrix:
            row = f"| {prob_labels[p]} |"
            for m in top_methods:
                val = matrix[p].get(m, 0)
                cell = f" **{val}** " if val > 10 else f" {val} " if val > 0 else " · "
                row += cell + "|"
            w(row)

    w()
    w("---")
    w()

    # --- Emerging/Declining Methods ---
    w("## 8. 방법론 트렌드 (Emerging vs Declining)")
    w()

    if emerging_methods:
        w("### 급부상 (Emerging, post-2020 성장률 > 2.0x)")
        w()
        w("| 방법론 | pre-2020 | post-2020 | 성장률 | 비율/100편 변화 |")
        w("|--------|----------|-----------|--------|----------------|")
        for m_name, info in emerging_methods[:8]:
            pre = info.get("pre2020_count", 0)
            post = info.get("post2020_count", 0)
            ratio = info.get("ratio", 0)
            pre_rate = info.get("pre2020_rate_per100", 0)
            post_rate = info.get("post2020_rate_per100", 0)
            w(f"| {abbrev(m_name)} | {pre} | {post} | {ratio:.1f}x | "
              f"{pre_rate:.1f} → {post_rate:.1f} |")
        w()

    declining = [
        (m, info) for m, info in emerging.items()
        if isinstance(info, dict) and info.get("trend") == "declining"
    ]
    declining.sort(key=lambda x: x[1].get("ratio", 1))

    if declining:
        w("### 하락 (Declining)")
        w()
        w("| 방법론 | pre-2020 | post-2020 | 감소율 |")
        w("|--------|----------|-----------|--------|")
        for m_name, info in declining[:5]:
            pre = info.get("pre2020_count", 0)
            post = info.get("post2020_count", 0)
            ratio = info.get("ratio", 0)
            w(f"| {abbrev(m_name)} | {pre} | {post} | {ratio:.2f}x |")
        w()

    w("---")
    w()

    # --- Summary interpretation (data-driven) ---
    w("## 9. 종합 해석")
    w()
    w("### 핵심 메시지")
    w()
    w("Virtual cell 연구 지형은 다음과 같은 주요 흐름으로 요약된다:")
    w()

    # Generate data-driven insights
    synthesis_insights = _generate_synthesis(data)
    for insight in synthesis_insights:
        w(insight)
        w()

    w("### 연구 기회")
    w()
    if gaps:
        gap_sum = sum(g.get('opportunity_score', 0) for g in gaps[:10])
        top_gap = gaps[0]
        top_gap_method = top_gap.get('method', '?')
        top_gap_problem = top_gap.get('problem', '?')

        w(f"상위 10개 연구 공백의 기회 점수 합계는 {gap_sum:,}이며, "
          f"이 중 **{top_gap_problem}**에 **{top_gap_method}**을(를) 적용하는 연구가 "
          f"가장 큰 기회를 제공한다 (기회 점수: {top_gap.get('opportunity_score', 0):,}). "
          f"이러한 공백 영역으로의 확장이 높은 영향력을 가질 것으로 예상된다.")
    else:
        w("연구 공백 데이터가 부족하여 기회 분석을 생략합니다.")
    w()
    w("### 한계")
    w()
    w("- 이 분석은 OpenAlex 검색 결과에 기반하며, 모든 관련 논문을 포함하지는 않는다.")
    w("- 방법론 분류는 LLM 기반 추출이며, 일부 오분류가 존재할 수 있다.")
    w("- 인용 수는 출판 시기에 따라 편향되므로, 최신 논문의 영향력이 과소평가될 수 있다.")
    w("- 도메인 분류는 PaperSift의 Leiden 클러스터링 결과에 기반하며, "
      "연구자 커뮤니티의 실제 분류와 차이가 있을 수 있다.")
    w()
    w("---")
    w()
    w("## 데이터 출처")
    w()
    w("| 파일 | 설명 | 크기 |")
    w("|------|------|------|")
    w("| `landscape_map.json` | 3-level MECE 계층 구조 | 569KB |")
    w("| `method_flows.json` | 22개 방법론 수렴/발산 분석 | 60KB |")
    w("| `trend_analysis.json` | 시간별 트렌드, Problem×Method 매트릭스 | 28KB |")
    w("| `hypotheses.json` | 10개 가설, 공백 분석 | 50KB |")
    w("| `papers_enriched.json` | 3,070편 메타데이터 (1,998편 biology) | 9.8MB |")
    w()
    w(f"*이 보고서는 `results/virtual-cell-sweep/` 디렉토리의 분석 데이터에서 "
      f"자동 생성되었습니다. 생성일: {datetime.now().strftime('%Y-%m-%d')}*")

    # Write
    content = "\n".join(lines)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)

    word_count = len(content.split())
    print(f"Markdown report: {out_path} ({word_count} words)", file=sys.stderr)
    return out_path


# ---------------------------------------------------------------------------
# Layer 3: HTML dashboard
# ---------------------------------------------------------------------------

def generate_html(data: dict, output_dir: Path, offline: bool = False) -> Path:
    """Generate standalone interactive HTML dashboard.

    Args:
        data: Loaded analysis data
        output_dir: Output directory
        offline: If True, inline Plotly.js (~3.5MB). If False, use CDN (default)
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "landscape-dashboard.html"

    landscape = data["landscape"]
    flows = data["flows"]
    trends = data["trends"]
    hyp = data["hypotheses"]
    doi_index = data["doi_index"]

    domains = landscape["level_0"]["domains"]
    total_papers = landscape["metadata"]["total_biology_papers"]
    total_methods = flows["summary_stats"]["total_methods_analyzed"]
    n_hypotheses = len(hyp["hypotheses"])

    # --- Prepare chart data ---

    # 1. Sankey: top 8 methods -> 5 domains
    domain_id_to_name = {did: dom["name"] for did, dom in domains.items()}
    cluster_to_domain = {str(dom["cluster_id"]): did for did, dom in domains.items()}
    # Also add "C"-prefixed keys for method_flows.json compatibility
    cluster_to_domain.update({f"C{dom['cluster_id']}": did for did, dom in domains.items()})

    method_flows = flows["method_flows"]
    # Sort methods by total papers
    method_totals = {}
    for mname, mdata in method_flows.items():
        total = sum(mdata.get("cluster_distribution", {}).values())
        method_totals[mname] = total
    top8_methods = sorted(method_totals, key=method_totals.get, reverse=True)[:8]

    sankey_nodes = list(top8_methods) + [domain_id_to_name[d] for d in sorted(domains.keys())]
    sankey_source = []
    sankey_target = []
    sankey_value = []

    domain_colors = {
        "D0": "#e74c3c", "D1": "#3498db", "D3": "#2ecc71",
        "D5": "#f39c12", "D7": "#9b59b6",
    }

    for mi, mname in enumerate(top8_methods):
        dist = method_flows[mname].get("cluster_distribution", {})
        for cid, count in dist.items():
            did = cluster_to_domain.get(str(cid))
            if did and did in domain_id_to_name:
                ti = len(top8_methods) + sorted(domains.keys()).index(did)
                sankey_source.append(mi)
                sankey_target.append(ti)
                sankey_value.append(count)

    sankey_data = json.dumps({
        "nodes": sankey_nodes,
        "source": sankey_source,
        "target": sankey_target,
        "value": sankey_value,
    })

    # 2. Temporal stacked area chart
    temporal = trends.get("task2_temporal_evolution", {})
    periods = list(temporal.keys())
    # Find top 8 methods by total across periods
    method_period_totals: dict[str, int] = {}
    for period, pdata in temporal.items():
        methods_data = pdata if isinstance(pdata, dict) and "methods" not in pdata else pdata.get("methods", pdata)
        if isinstance(methods_data, dict):
            for m, c in methods_data.items():
                if m in ("total", "period"):
                    continue
                method_period_totals[m] = method_period_totals.get(m, 0) + (c if isinstance(c, int) else 0)
    top8_temporal = sorted(method_period_totals, key=method_period_totals.get, reverse=True)[:8]

    temporal_traces = []
    for m in top8_temporal:
        y_values = []
        for period in periods:
            pdata = temporal[period]
            methods_data = pdata if isinstance(pdata, dict) and "methods" not in pdata else pdata.get("methods", pdata)
            y_values.append(methods_data.get(m, 0) if isinstance(methods_data, dict) else 0)
        temporal_traces.append({"name": abbrev(m), "y": y_values})

    temporal_data = json.dumps({"periods": periods, "traces": temporal_traces})

    # 3. Gap heatmap (10 rows x top 10 methods)
    matrix = trends.get("task5_problem_method_matrix", {})
    hm_method_totals: dict[str, int] = {}
    for p, methods in matrix.items():
        for m, c in methods.items():
            hm_method_totals[m] = hm_method_totals.get(m, 0) + c
    top10_hm_methods = sorted(hm_method_totals, key=hm_method_totals.get, reverse=True)[:10]

    hm_problems = list(matrix.keys())
    hm_y_labels = [p.split(": ")[1] if ": " in p else p for p in hm_problems]
    hm_z = [[matrix[p].get(m, 0) for m in top10_hm_methods] for p in hm_problems]
    hm_x_labels = [abbrev(m) for m in top10_hm_methods]

    heatmap_data = json.dumps({
        "x": hm_x_labels,
        "y": hm_y_labels,
        "z": hm_z,
    })

    # 4. Hypothesis cards (top 5)
    all_hyps = hyp["hypotheses"]
    high = [h for h in all_hyps if h["confidence"] == "High"]
    medium = sorted(
        [h for h in all_hyps if h["confidence"] == "Medium"],
        key=lambda h: len(h.get("supporting_dois", [])),
        reverse=True,
    )
    selected_hyps = high + medium[:5 - len(high)]
    hyp_cards_data = []
    for h in selected_hyps:
        evidence = h.get("evidence", {})
        support = evidence.get("support", str(evidence)) if isinstance(evidence, dict) else str(evidence)
        hyp_cards_data.append({
            "id": h["id"],
            "title": h["title"],
            "confidence": h["confidence"],
            "hypothesis": h.get("hypothesis", ""),
            "support": support[:300],
            "impact": h.get("impact", "")[:200],
        })
    hyp_cards_json = json.dumps(hyp_cards_data, ensure_ascii=False)

    # 5. Hierarchy tree data
    tree_data = []
    sorted_domains = sorted(domains.items(), key=lambda x: x[1]["paper_count"], reverse=True)
    for did, dom in sorted_domains:
        pcs = sorted(dom["problem_categories"].items(),
                      key=lambda x: x[1]["paper_count"], reverse=True)
        problems = []
        for pname, pdata in pcs[:8]:
            methods_list = []
            meth = pdata.get("methods", {})
            sorted_m = sorted(
                [(m, md["paper_count"]) for m, md in meth.items() if m != "Unspecified"],
                key=lambda x: x[1], reverse=True
            )[:5]
            for mname, mcount in sorted_m:
                methods_list.append({"name": mname, "count": mcount})
            problems.append({
                "name": pname,
                "count": pdata["paper_count"],
                "trend": pdata.get("temporal_trend", "stable"),
                "methods": methods_list,
            })
        tree_data.append({
            "id": did,
            "name": dom["name"],
            "count": dom["paper_count"],
            "trend": dom.get("temporal_trend", "stable"),
            "color": domain_colors.get(did, "#888"),
            "problems": problems,
        })
    tree_json = json.dumps(tree_data, ensure_ascii=False)

    # --- Plotly.js inclusion (CDN vs offline) ---
    if offline:
        from plotly.offline import get_plotlyjs
        plotly_script = f'<script>{get_plotlyjs()}</script>'
    else:
        plotly_script = '<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>'

    # --- Build HTML ---
    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Virtual Cell 연구 지형도</title>
{plotly_script}
<style>
:root {{
  --bg: #ffffff;
  --bg2: #f8f9fa;
  --text: #212529;
  --text2: #495057;
  --card: #ffffff;
  --border: #dee2e6;
  --accent: #3498db;
  --accent2: #2ecc71;
  --shadow: rgba(0,0,0,0.08);
}}
[data-theme="dark"] {{
  --bg: #1a1a2e;
  --bg2: #16213e;
  --text: #e8e8e8;
  --text2: #adb5bd;
  --card: #0f3460;
  --border: #2c3e6b;
  --accent: #e94560;
  --accent2: #53d769;
  --shadow: rgba(0,0,0,0.3);
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.6;
  transition: background 0.3s, color 0.3s;
}}
.container {{ max-width: 1200px; margin: 0 auto; padding: 0 20px; }}

/* Hero */
.hero {{
  background: linear-gradient(135deg, #3498db, #2c3e50);
  color: white;
  padding: 48px 0;
  text-align: center;
}}
[data-theme="dark"] .hero {{
  background: linear-gradient(135deg, #e94560, #1a1a2e);
}}
.hero h1 {{ font-size: 2.2rem; margin-bottom: 8px; }}
.hero .subtitle {{ opacity: 0.85; font-size: 1.1rem; }}
.stats {{
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-top: 32px;
}}
.stat-card {{
  background: rgba(255,255,255,0.15);
  border-radius: 12px;
  padding: 20px;
  backdrop-filter: blur(10px);
}}
.stat-card .number {{ font-size: 2rem; font-weight: 700; }}
.stat-card .label {{ font-size: 0.85rem; opacity: 0.8; }}

/* Theme toggle */
.theme-toggle {{
  position: fixed;
  top: 16px;
  right: 16px;
  z-index: 1000;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 12px;
  cursor: pointer;
  font-size: 1.2rem;
  box-shadow: 0 2px 8px var(--shadow);
}}

/* Sections */
section {{
  padding: 40px 0;
  border-bottom: 1px solid var(--border);
}}
section h2 {{
  font-size: 1.5rem;
  margin-bottom: 24px;
  color: var(--accent);
}}

/* Tree */
.tree details {{
  margin-left: 20px;
  padding: 4px 0;
}}
.tree summary {{
  cursor: pointer;
  padding: 6px 10px;
  border-radius: 6px;
  font-weight: 500;
  transition: background 0.2s;
}}
.tree summary:hover {{ background: var(--bg2); }}
.tree .badge {{
  display: inline-block;
  background: var(--accent);
  color: white;
  border-radius: 10px;
  padding: 1px 8px;
  font-size: 0.75rem;
  margin-left: 6px;
}}
.tree .trend {{ font-size: 0.8rem; margin-left: 4px; }}
.tree .method-item {{
  margin-left: 40px;
  padding: 2px 0;
  color: var(--text2);
  font-size: 0.9rem;
}}

/* Charts */
.chart-grid {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
}}
.chart-box {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 2px 8px var(--shadow);
  min-height: 400px;
}}
.chart-box.full {{ grid-column: 1 / -1; }}
.chart-box h3 {{
  font-size: 1.1rem;
  margin-bottom: 12px;
  color: var(--text);
}}

/* Hypothesis cards */
.hyp-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 16px;
}}
.hyp-card {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 2px 8px var(--shadow);
  transition: transform 0.2s;
}}
.hyp-card:hover {{ transform: translateY(-2px); }}
.hyp-header {{ display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }}
.hyp-id {{
  font-weight: 700;
  font-size: 1rem;
  color: var(--accent);
}}
.confidence {{
  display: inline-block;
  padding: 2px 10px;
  border-radius: 10px;
  font-size: 0.75rem;
  font-weight: 600;
}}
.confidence.high {{ background: #d4edda; color: #155724; }}
.confidence.medium {{ background: #fff3cd; color: #856404; }}
.confidence.low {{ background: #f8d7da; color: #721c24; }}
[data-theme="dark"] .confidence.high {{ background: #1e4d2b; color: #a3d9a5; }}
[data-theme="dark"] .confidence.medium {{ background: #4d3a00; color: #ffd966; }}
[data-theme="dark"] .confidence.low {{ background: #4d1c24; color: #f5a3ab; }}
.hyp-title {{ font-weight: 600; font-size: 0.95rem; margin-bottom: 8px; }}
.hyp-text {{ font-size: 0.85rem; color: var(--text2); }}
.hyp-details {{ display: none; margin-top: 10px; font-size: 0.85rem; }}
.hyp-card.expanded .hyp-details {{ display: block; }}

/* Footer */
footer {{
  text-align: center;
  padding: 24px;
  color: var(--text2);
  font-size: 0.85rem;
}}

/* Responsive */
@media (max-width: 768px) {{
  .stats {{ grid-template-columns: repeat(2, 1fr); }}
  .chart-grid {{ grid-template-columns: 1fr; }}
  .hero h1 {{ font-size: 1.5rem; }}
  .stat-card .number {{ font-size: 1.5rem; }}
}}
@media print {{
  .theme-toggle {{ display: none; }}
  .hero {{ background: #3498db !important; -webkit-print-color-adjust: exact; }}
}}
</style>
</head>
<body>

<button class="theme-toggle" onclick="toggleTheme()" title="테마 전환">🌓</button>

<!-- Hero -->
<div class="hero">
  <div class="container">
    <h1>Virtual Cell 연구 지형도</h1>
    <p class="subtitle">{total_papers:,}편의 생물학 논문에 대한 체계적 분석</p>
    <div class="stats">
      <div class="stat-card">
        <div class="number">{total_papers:,}</div>
        <div class="label">Biology Papers</div>
      </div>
      <div class="stat-card">
        <div class="number">{len(domains)}</div>
        <div class="label">Research Domains</div>
      </div>
      <div class="stat-card">
        <div class="number">{total_methods}</div>
        <div class="label">Methods Analyzed</div>
      </div>
      <div class="stat-card">
        <div class="number">{n_hypotheses}</div>
        <div class="label">Research Hypotheses</div>
      </div>
    </div>
  </div>
</div>

<!-- Hierarchy Tree -->
<section>
  <div class="container">
    <h2>연구 계층 구조</h2>
    <div class="tree" id="tree-container"></div>
  </div>
</section>

<!-- Charts -->
<section>
  <div class="container">
    <h2>방법론 분석</h2>
    <div class="chart-grid">
      <div class="chart-box">
        <h3>방법론 → 도메인 흐름 (Sankey)</h3>
        <div id="sankey-chart"></div>
      </div>
      <div class="chart-box">
        <h3>시간별 방법론 추이</h3>
        <div id="temporal-chart"></div>
      </div>
      <div class="chart-box full">
        <h3>문제 x 방법론 매트릭스</h3>
        <div id="heatmap-chart"></div>
      </div>
    </div>
  </div>
</section>

<!-- Hypotheses -->
<section>
  <div class="container">
    <h2>연구 가설</h2>
    <div class="hyp-grid" id="hyp-container"></div>
  </div>
</section>

<footer>
  <div class="container">
    생성일: {datetime.now().strftime('%Y-%m-%d')} |
    데이터: results/virtual-cell-sweep/ |
    PaperSift Landscape Report
  </div>
</footer>

<script>
// --- Theme ---
function toggleTheme() {{
  const body = document.body;
  const isDark = body.getAttribute('data-theme') === 'dark';
  body.setAttribute('data-theme', isDark ? '' : 'dark');
  localStorage.setItem('theme', isDark ? 'light' : 'dark');
  // Re-layout charts for theme
  const charts = ['sankey-chart', 'temporal-chart', 'heatmap-chart'];
  charts.forEach(id => {{
    const el = document.getElementById(id);
    if (el && el.data) {{
      Plotly.relayout(id, {{
        'paper_bgcolor': isDark ? '#ffffff' : '#0f3460',
        'plot_bgcolor': isDark ? '#ffffff' : '#0f3460',
        'font.color': isDark ? '#212529' : '#e8e8e8',
      }});
    }}
  }});
}}
if (localStorage.getItem('theme') === 'dark') {{
  document.body.setAttribute('data-theme', 'dark');
}}

// --- Tree ---
const treeData = {tree_json};
const trendIcon = {{'growing': '▲', 'declining': '▼', 'stable': '—'}};
function buildTree() {{
  const container = document.getElementById('tree-container');
  let html = '<details open><summary><strong>Virtual Cell Research</strong> <span class="badge">{total_papers:,}</span></summary>';
  treeData.forEach(domain => {{
    html += `<details><summary style="border-left:3px solid ${{domain.color}}; padding-left:8px">`;
    html += `<strong>${{domain.id}}: ${{domain.name}}</strong> <span class="badge">${{domain.count}}</span>`;
    html += `<span class="trend">${{trendIcon[domain.trend] || '—'}}</span></summary>`;
    html += `<div style="font-size:11px;color:var(--subtext,#888);margin:2px 0 4px 11px">하위 분류는 논문 중복 포함</div>`;
    domain.problems.forEach(prob => {{
      html += `<details><summary>${{prob.name}} <span class="badge">${{prob.count}}</span>`;
      html += `<span class="trend">${{trendIcon[prob.trend] || '—'}}</span></summary>`;
      prob.methods.forEach(m => {{
        html += `<div class="method-item">· ${{m.name}}: ${{m.count}}편</div>`;
      }});
      html += '</details>';
    }});
    html += '</details>';
  }});
  html += '</details>';
  container.innerHTML = html;
}}
buildTree();

// --- Sankey ---
const sankeyData = {sankey_data};
const domainColors = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6'];
const methodColors = ['#95a5a6', '#7f8c8d', '#bdc3c7', '#85929e', '#aab7b8', '#a3b1bf', '#99a3ad', '#8e979f'];
Plotly.newPlot('sankey-chart', [{{
  type: 'sankey',
  orientation: 'h',
  node: {{
    pad: 15,
    thickness: 20,
    line: {{ color: 'rgba(0,0,0,0.2)', width: 0.5 }},
    label: sankeyData.nodes,
    color: sankeyData.nodes.map((n, i) => i < {len(top8_methods)} ? methodColors[i % methodColors.length] : domainColors[i - {len(top8_methods)}])
  }},
  link: {{
    source: sankeyData.source,
    target: sankeyData.target,
    value: sankeyData.value,
    color: sankeyData.target.map(t => {{
      const di = t - {len(top8_methods)};
      return domainColors[di] ? domainColors[di] + '40' : '#cccccc40';
    }})
  }}
}}], {{
  margin: {{ t: 10, l: 10, r: 10, b: 10 }},
  paper_bgcolor: 'rgba(0,0,0,0)',
  font: {{ size: 11, color: getComputedStyle(document.body).getPropertyValue('--text').trim() || '#212529' }}
}}, {{ responsive: true }});

// --- Temporal ---
const temporalData = {temporal_data};
const areaColors = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6', '#1abc9c', '#e67e22', '#34495e'];
const temporalTraces = temporalData.traces.map((t, i) => ({{
  x: temporalData.periods,
  y: t.y,
  name: t.name,
  type: 'scatter',
  mode: 'lines',
  stackgroup: 'one',
  fillcolor: areaColors[i % areaColors.length] + '80',
  line: {{ color: areaColors[i % areaColors.length], width: 1 }}
}}));
Plotly.newPlot('temporal-chart', temporalTraces, {{
  margin: {{ t: 10, l: 50, r: 10, b: 40 }},
  paper_bgcolor: 'rgba(0,0,0,0)',
  plot_bgcolor: 'rgba(0,0,0,0)',
  yaxis: {{ title: '논문 수', gridcolor: 'rgba(128,128,128,0.2)' }},
  xaxis: {{ gridcolor: 'rgba(128,128,128,0.2)' }},
  font: {{ size: 11, color: getComputedStyle(document.body).getPropertyValue('--text').trim() || '#212529' }},
  legend: {{ orientation: 'h', y: -0.15 }},
  hovermode: 'x unified'
}}, {{ responsive: true }});

// --- Heatmap ---
const heatmapData = {heatmap_data};
Plotly.newPlot('heatmap-chart', [{{
  type: 'heatmap',
  z: heatmapData.z,
  x: heatmapData.x,
  y: heatmapData.y,
  colorscale: [
    [0, '#f8f9fa'],
    [0.01, '#fff3cd'],
    [0.1, '#ffc107'],
    [0.3, '#fd7e14'],
    [0.6, '#dc3545'],
    [1, '#7b2d26']
  ],
  hoverongaps: false,
  hovertemplate: '%{{y}}<br>%{{x}}<br>논문 수: %{{z}}<extra></extra>'
}}], {{
  margin: {{ t: 10, l: 200, r: 20, b: 80 }},
  paper_bgcolor: 'rgba(0,0,0,0)',
  plot_bgcolor: 'rgba(0,0,0,0)',
  xaxis: {{ tickangle: -45 }},
  font: {{ size: 11, color: getComputedStyle(document.body).getPropertyValue('--text').trim() || '#212529' }}
}}, {{ responsive: true }});

// --- Hypothesis cards ---
const hypData = {hyp_cards_json};
const confClass = {{'High': 'high', 'Medium': 'medium', 'Low': 'low'}};
const hypContainer = document.getElementById('hyp-container');
hypData.forEach(h => {{
  const card = document.createElement('div');
  card.className = 'hyp-card';
  card.onclick = () => card.classList.toggle('expanded');
  card.innerHTML = `
    <div class="hyp-header">
      <span class="hyp-id">${{h.id}}</span>
      <span class="confidence ${{confClass[h.confidence]}}">${{h.confidence}}</span>
    </div>
    <div class="hyp-title">${{h.title}}</div>
    <div class="hyp-text">${{h.hypothesis.substring(0, 120)}}...</div>
    <div class="hyp-details">
      <p><strong>근거:</strong> ${{h.support}}</p>
      <p style="margin-top:8px"><strong>영향:</strong> ${{h.impact}}</p>
    </div>
  `;
  hypContainer.appendChild(card);
}});
</script>
</body>
</html>"""

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"HTML dashboard: {out_path} ({size_mb:.1f} MB)", file=sys.stderr)
    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate landscape report from PaperSift analysis data"
    )
    parser.add_argument(
        "--input-dir", type=Path,
        default=Path("results/virtual-cell-sweep"),
        help="Input directory with JSON data files (default: results/virtual-cell-sweep)",
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=Path("reports/virtual-cell-sweep"),
        help="Output directory for reports (default: reports/virtual-cell-sweep)",
    )
    parser.add_argument("--markdown", action="store_true", help="Generate markdown report")
    parser.add_argument("--html", action="store_true", help="Generate HTML dashboard")
    parser.add_argument("--all", action="store_true", help="Generate both markdown and HTML")
    parser.add_argument(
        "--offline", action="store_true", default=False,
        help="Inline Plotly.js for offline viewing (adds ~3.5MB, default: use CDN)"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not args.markdown and not args.html and not args.all:
        print("No output format specified. Use --markdown, --html, or --all", file=sys.stderr)
        sys.exit(1)

    print(f"Loading data from {args.input_dir}...", file=sys.stderr)
    data = load_data(args.input_dir)
    print(f"Loaded {len(data['papers']):,} papers, {len(data['doi_index']):,} DOIs", file=sys.stderr)

    if args.markdown or args.all:
        generate_markdown(data, args.output_dir)

    if args.html or args.all:
        generate_html(data, args.output_dir, offline=args.offline)

    print("Done.", file=sys.stderr)


if __name__ == "__main__":
    main()
