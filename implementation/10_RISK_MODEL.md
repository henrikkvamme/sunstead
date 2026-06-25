# Risk Model

The first risk model is transparent and evidence-backed. It must explain why a score changed and which source data supports it. Future ML can add features, but not bypass provenance.

## Risk Scopes

Risk can be scored for:

- Drug
- ActiveIngredient
- Excipient
- RawMaterial
- ChemicalInput
- Manufacturer
- Supplier
- Facility
- MedicalDevice
- DeviceCategory
- Region
- Port
- TransportRoute
- Commodity
- RiskCase

## Risk Categories

Required categories:

- drug risk
- active ingredient risk
- manufacturer risk
- supplier risk
- facility risk
- medical device risk
- region/port/logistics risk
- commodity/input risk
- shortage risk
- recall/quality risk
- manufacturing disruption risk
- labor risk
- disaster risk
- regulatory risk
- graph dependency risk
- confidence-adjusted risk

## Score Shape

Use 0 to 100 component and final scores.

```text
base_score = weighted_sum(component_scores)
evidence_adjusted = base_score * evidence_confidence_factor
recency_adjusted = evidence_adjusted * recency_factor
final_score = clamp(evidence_adjusted + recency_adjusted + graph_amplification - mitigation_credit, 0, 100)
```

Confidence is separate:

```text
confidence = source_reliability * extraction_confidence * entity_resolution_confidence * evidence_coverage * graph_path_confidence
```

Display both score and confidence. A high score with low confidence is a review priority, not a firm verdict.

## Component Scores

### Shortage Risk

Inputs:

- official shortage status
- shortage duration
- number of affected presentations
- therapeutic alternatives available if source supports it
- affected manufacturer count
- affected ingredient dependency
- current/resolved status
- update recency

Evidence:

- FDA shortage pages/downloads
- openFDA NDC
- source evidence spans

### Recall and Quality Risk

Inputs:

- recall class
- product quantity
- distribution breadth
- reason for recall
- recurrence by manufacturer/facility
- related warning letters or inspections when available
- affected devices/drugs

Evidence:

- openFDA enforcement
- FDA warning/inspection sources when added

### Regulatory Risk

Inputs:

- warning letters
- import alerts
- enforcement actions
- inspection outcomes
- unresolved notices
- agency severity

Evidence:

- FDA sources
- SEC filings if company discloses regulatory proceedings

### Manufacturing Disruption Risk

Inputs:

- facility disaster proximity
- facility strike/labor event
- quality event
- production concentration
- single-source manufacturer signals
- delayed or discontinued products

Evidence:

- GDACS
- ReliefWeb
- GDELT/news
- FDA shortages
- SEC disclosures

### Supplier Risk

Inputs:

- supplier centrality in graph
- history of recalls/quality issues
- geographic exposure
- financial distress signals from filings
- dependency count
- weak or low-confidence supplier relationships

Evidence:

- graph paths
- source documents
- agent findings

### Facility Risk

Inputs:

- facility role in manufacturing
- products/ingredients linked
- location exposure
- regulatory events
- recall recurrence
- logistics access

### Medical Device Risk

Inputs:

- device recalls
- manufacturer/facility risk
- category criticality
- component/input dependency
- regulatory notices

### Region/Port/Logistics Risk

Inputs:

- disasters
- strikes
- route disruptions
- port proximity to facilities
- energy/fuel price pressure
- commodity or freight proxy changes

### Commodity/Input Risk

Inputs:

- price observation z-score
- month-over-month change
- volatility
- input criticality
- linked products and facilities
- import/trade concentration when available

## Graph Dependency Risk

Graph amplification uses:

- number of downstream products
- number of dependent ingredients/devices
- path confidence
- relationship recency
- supplier/facility centrality
- alternative path count
- single-source indicators

Example:

```text
graph_amplification =
  min(20, log1p(affected_downstream_count) * 4)
  * average_path_confidence
  * single_source_multiplier
```

## Evidence Coverage

Evidence coverage factors:

- source reliability
- number of independent sources
- evidence span quality
- freshness
- directness of evidence
- contradiction count

Direct official source evidence outranks inferred news-only evidence.

## Risk Case Lifecycle

Statuses:

- `candidate`
- `investigating`
- `watch`
- `confirmed`
- `dismissed`
- `resolved`
- `needs_human_review`

Lifecycle:

1. Risk signal creates a persisted `risk_candidates` row and `risk.candidates` event.
2. Candidate is scored deterministically with evidence span IDs and scoped graph keys.
3. Case is created if score or severity threshold is crossed.
4. Investigation swarm gathers graph context and evidence.
5. Critic verifies assumptions.
6. Verdict agent emits verdict.
7. Alert worker emits alert if thresholds are crossed.
8. Case is re-opened or updated when new evidence arrives.

## Verdict Types

- `confirmed_risk`
- `possible_risk`
- `watch`
- `dismissed`
- `resolved`

Verdict must include:

- score
- confidence
- severity
- key drivers
- supporting evidence spans
- limitations
- affected entities
- recommended operational follow-up

No verdict may include medical advice or clinical guidance.

## Feature History

Store feature snapshots for future ML readiness:

- `risk_feature_snapshots` should be added in phase 2 if not included in initial migrations.
- Fields: scope, feature name, value, window, source evidence, computed_at, feature_version.

Do not train ML until:

- enough historical outcomes exist
- labels are reviewed
- leakage analysis is complete
- model cards and governance are defined

## Initial Alert Thresholds

Defaults:

- Critical: score >= 90 and confidence >= 0.70
- High: score >= 75 and confidence >= 0.65
- Medium: score >= 55 and confidence >= 0.55
- Watch: score >= 40 or confidence < threshold but evidence indicates possible issue

Human review:

- any critical case with confidence < 0.80
- any high-impact entity with conflicting evidence
- any case driven primarily by unverified news

## Risk Explainability

Every case explanation must be reconstructable from:

- `risk_cases.component_scores`
- `agent_findings`
- `evidence_spans`
- graph paths
- source documents
- extraction runs

Dashboard summaries can be compact, but the CLI `explain-case` must show:

- score formula
- component values
- source documents
- evidence spans
- graph paths
- confidence calculation
- limitations and unresolved conflicts
