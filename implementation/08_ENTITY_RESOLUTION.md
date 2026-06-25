# Entity Resolution

Entity resolution converts extracted mentions into canonical entities without losing uncertainty. The system must prefer deterministic identifiers, preserve aliases, and route ambiguous cases to human review.

## Entity Types

Initial canonical entity types:

- `Drug`
- `NDC`
- `ActiveIngredient`
- `Excipient`
- `RawMaterial`
- `ChemicalInput`
- `Manufacturer`
- `Supplier`
- `Facility`
- `MedicalDevice`
- `DeviceCategory`
- `RegulatoryAgency`
- `Country`
- `Region`
- `City`
- `Port`
- `TransportRoute`
- `Commodity`

Event-like objects such as `Shortage`, `Recall`, `RegulatoryNotice`, `NewsEvent`, `DisasterEvent`, `StrikeEvent`, `PriceObservation`, and `RiskCase` may also get canonical keys but should be handled with event-specific identity rules.

## Canonical Keys

Use deterministic keys where possible:

- NDC package/product: `ndc:<product_ndc>` or `ndc_package:<package_ndc>`
- openFDA recall: `openfda_recall:<recall_number>`
- FDA establishment identifier: `fei:<fei_number>` when available
- SEC company: `sec_cik:<10_digit_cik>`
- country: `iso3166:<alpha2>`
- port: `unlocode:<code>` when available
- commodity: `commodity:<curated_slug>`

When no official ID exists:

- normalize name
- include type
- include source family if needed
- avoid over-specific keys that block later merging

Example:

```text
manufacturer:name_hash:<normalized_name_hash>
facility:name_location_hash:<normalized_name>|<city>|<country>
```

## Normalization

Name normalization should:

- lowercase
- Unicode normalize
- trim whitespace
- collapse punctuation
- normalize common corporate suffixes for matching while preserving display names
- normalize abbreviations such as `inc`, `corp`, `ltd`, `gmbh`
- preserve clinically or chemically meaningful tokens
- preserve NDC hyphen formats in original aliases while creating normalized digit forms

Do not normalize away:

- dosage forms
- salts, hydrates, or stereochemistry for ingredients
- facility location qualifiers
- device model identifiers

## Matching Pipeline

1. Deterministic identifiers:
   - NDCs
   - FEI or registration IDs
   - CIK
   - DUNS or GLN if later licensed
   - official recall numbers

2. Exact normalized alias:
   - match `entity_aliases.normalized_alias`
   - require same entity type

3. Entity-type-specific rules:
   - `Drug`: NDC, application number, proprietary name plus active ingredient.
   - `ActiveIngredient`: normalized chemical name, UNII if available.
   - `Manufacturer`: labeler codes, CIK, FEI, official company names.
   - `Facility`: FEI plus address; otherwise name plus geocoded location.
   - `Device`: listing number, product code, device name, manufacturer.

4. `pg_trgm` fuzzy candidates:
   - retrieve top N by trigram similarity.
   - require type-specific minimum thresholds.

5. pgvector semantic candidates:
   - use mention context plus entity attributes.
   - useful for aliases and multilingual variants.

6. Graph context:
   - compare known relationships such as manufacturer, country, product, active ingredient, facility, device category.

7. Agent-assisted resolution:
   - only for candidates within uncertainty band.
   - output typed decision.

8. Human review:
   - conflicts, low confidence, high-impact entities, or potential company/facility merges.

## Confidence Thresholds

Initial defaults:

- deterministic official ID: `1.00`
- exact alias same type: `0.95`
- trigram high match plus compatible context: `0.88`
- vector plus compatible graph context: `0.82`
- agent-assisted accepted match: `0.78` minimum
- below `0.78`: do not merge automatically
- `0.70` to `0.88` for high-impact entities: mark `needs_review`

High-impact entities:

- manufacturers
- suppliers
- facilities
- active ingredients
- medical devices
- risk case scopes

## Conflict Handling

Never overwrite canonical truth silently. If conflicting source assertions appear:

- create entity mention with `resolution_status='conflict'`
- attach evidence spans
- create `human_feedback` review task
- set `canonical_entities.needs_review=true`
- preserve both source assertions in attributes or relationship versions

Examples:

- same FEI with different company names
- facility address changes
- manufacturer subsidiary versus parent company
- product name reused by different labelers
- active ingredient synonyms that are not chemically equivalent

## Subsidiaries and Corporate Families

Represent subsidiaries explicitly:

- company A is not company B because names are similar.
- parent/subsidiary relationships require official evidence.
- keep `Manufacturer` and `Supplier` roles separate from `Company` identity where useful.

Future graph relationship:

- `OWNS`
- `SUBSIDIARY_OF`
- `AFFILIATED_WITH`

These are not in the initial required relationship list but may be added later with provenance.

## Human Review Workflow

Review queue criteria:

- confidence below threshold
- conflicting deterministic identifiers
- multiple candidates within 0.05 confidence
- high graph blast radius
- new canonical entity from sparse evidence
- agent disagreement

Reviewer actions:

- approve match
- reject match
- create new entity
- merge entities
- split entity
- add alias
- mark source assertion incorrect

Every action writes `human_feedback` and updates aliases/canonical records with audit metadata.

## Implementation Components

- `DeterministicMatcher`
- `AliasMatcher`
- `TrigramMatcher`
- `VectorMatcher`
- `GraphContextMatcher`
- `AgentResolutionReviewer`
- `HumanReviewQueue`
- `EntityResolutionService`

`EntityResolutionService.resolve_mention()` returns:

- canonical entity ID or proposal
- confidence
- method
- evidence
- review flags

## Idempotency

- Mention identity: raw document + chunk + character span + mention text + entity type.
- Canonical entity identity: `(entity_type, canonical_key)`.
- Alias identity: canonical entity + normalized alias + alias type.
- Resolution can be re-run with new algorithms; keep old mentions and update resolution fields with audit.

## Test Fixtures

Create fixtures for:

- exact NDC matches
- labeler/manufacturer aliases
- active ingredient spelling variants
- company suffix normalization
- facility same name in different countries
- same manufacturer with parent/subsidiary ambiguity
- false positive fuzzy match
- graph-context-assisted match
- conflict requiring review
