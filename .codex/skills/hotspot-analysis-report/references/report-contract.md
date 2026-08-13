# Report Contract

## Input contract

Require `topic`, `target_role`, `run`, and `events`. Each event must contain a title, value score, value level, action level, platform count, independent source count, growth value, review status, and at least one source with title and URL.

Program-owned fields are immutable: score, breakdown, tier, truth status, cluster confidence, source membership, timestamps, and human review.

## Eligibility

An event qualifies for decision analysis when it is manually approved, or when its tier is `high_value`/`watchlist` and it has at least two independent publishers. A candidate never qualifies for deep analysis solely because it ranks first.

When no event qualifies, select at most three candidates and generate a candidate-signal brief. Never call the selected candidates “the top hotspots”.

## Quality gate

Before writing:

1. Ensure every event has a source.
2. Ensure the title shares a named entity or clear event meaning with a source title. Fall back to the longest source title on mismatch.
3. Downgrade a single-source high-value event to candidate inside the report copy and record a warning.
4. State missing growth snapshots instead of interpreting absence as zero growth.
5. Treat Google Trends as an attention signal, never a factual primary source.

## Evidence language

- Verified fact: directly present in source fields; cite it.
- Reasonable inference: follows from cited facts but is not directly stated; label it.
- Insufficient evidence: required evidence is absent; do not fill the gap with general knowledge.

Forbidden without direct evidence: public sentiment, algorithmic amplification, social conflict, broad adoption, commercial value, technical strength, market leadership, causal trigger, probability, recovery period.

## Action scope

- Candidate: verify, monitor, find another independent publisher, record another snapshot, run a low-cost internal test.
- Watchlist: perform technical evaluation or limited internal pilot.
- High value: allocate follow-up resources only after evidence and risk review.
- Approved: may enter email or external delivery, subject to human confirmation.

## Required report structure

1. Title and metadata.
2. Outcome-first executive summary.
3. Data quality and run diagnostics.
4. Up to three priority evidence cards or qualified event analyses.
5. Recommended actions within tier limits.
6. Limitations and unknowns.
7. Method and version appendix.
8. Claim-level source mapping.
