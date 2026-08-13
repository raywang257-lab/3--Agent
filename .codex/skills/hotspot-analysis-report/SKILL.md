---
name: hotspot-analysis-report
description: Generate or revise source-backed TrendScope hotspot analysis reports and candidate-signal briefs from saved events, program scores, review states, run diagnostics, and public-source evidence. Use when asked to 生成分析报告、热点报告、候选线索简报、决策简报、总结热点、解释报告结论，或检查报告是否夸大、错配来源、缺少引用。
---

# Hotspot Analysis Report

Generate a decision-first, evidence-bounded Markdown report. Treat program scores and source records as immutable inputs; use AI only to organize supported language.

## Workflow

1. Load the monitoring task, latest completed current-version run, events, reviews, diagnostics, and source records.
2. Read [references/report-contract.md](references/report-contract.md) completely before deciding report scope or wording.
3. Run the quality gate before drafting:
   - Reject events without sources.
   - Replace semantically mismatched titles with the original source title.
   - Prevent a single-independent-source event from appearing as high value.
   - Preserve program score, level, source set, review status, and timestamps.
4. Select scope:
   - Include approved events.
   - Include high-value or watchlist events only when they have at least two independent publishers.
   - If none qualify, include at most three highest-scoring candidates as compact evidence cards.
5. Draft the first sentence as the actual outcome: state whether any event reached the high-value threshold.
6. Add claim-level citations using `[S1]`, `[S2]`, and map each label to one exact URL.
7. Validate forbidden language and action scope with `scripts/render_report.py` or the application quality gate.
8. Return the report plus limitations and generation mode. Never hide rule fallback or missing evidence.

## Output Rules

- Use “热点分析报告” only when a qualified high-value or watchlist event exists.
- Otherwise use “候选线索监测简报”.
- For each candidate include exactly: current tier, why selected, verified facts, unverified claims, upgrade conditions, allowed action, forbidden conclusion, sources.
- Do not generate deep causes, propagation mechanisms, impact forecasts, or scenarios for candidates.
- Do not use “快速增长” without comparable snapshots; “引发争议” without discussion evidence; “广泛采用” without adoption data; or “技术实力强” without technical evaluation.
- Do not recommend partnership, deployment, investment, strategic commitment, or external publication for candidates.
- State collection failures, single-source ratios, missing growth baselines, and scoring/prompt versions once in limitations.

## Bundled Resources

- Run `scripts/render_report.py --input payload.json --output report.md` for deterministic candidate briefs or qualified reports.
- Use [assets/report-template.md](assets/report-template.md) as the section order, not as evidence.
- Keep detailed eligibility and wording constraints in [references/report-contract.md](references/report-contract.md).
