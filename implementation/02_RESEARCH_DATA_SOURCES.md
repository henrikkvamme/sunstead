# Research: Data Sources

## Source Selection Principles

- Prefer authoritative primary sources.
- Store raw responses before transforming them.
- Model source licensing, robots, rate limits, cadence, and compliance in `data_sources`.
- Treat every source record as potentially corrected later. Preserve source timestamps and ingestion timestamps separately.
- Do not merge source assertions into canonical graph facts without evidence spans, extraction run IDs, and confidence.

## High-Priority Sources

| Source                              | Coverage                                                                                     | Auth and limits                                                                                                      | Format                                   | Cadence                                          | Priority | Difficulty     | Notes                                                                                                                                                                                                                            |
| ----------------------------------- | -------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- | ---------------------------------------- | ------------------------------------------------ | -------- | -------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| openFDA Drug NDC                    | NDC products, labelers, active ingredients, product metadata                                 | Free API key recommended. Standard limits: no key 240/min and 1,000/day per IP; key 240/min and 120,000/day per key. | JSON API and zipped JSON downloads       | Daily                                            | P0       | Low            | Endpoint: `https://api.fda.gov/drug/ndc.json`. Source docs: https://open.fda.gov/apis/drug/ndc/                                                                                                                                  |
| openFDA Drug Enforcement            | Drug recalls/enforcement reports                                                             | Same openFDA limits                                                                                                  | JSON API and zipped JSON downloads       | Weekly                                           | P0       | Low            | Endpoint: `https://api.fda.gov/drug/enforcement.json`. Docs: https://open.fda.gov/apis/drug/enforcement/                                                                                                                         |
| FDA Drug Shortages                  | Current/resolved shortages and discontinuations                                              | Public site, email notifications, downloadable current list                                                          | HTML and downloadable file               | Site-updated, source current as page states      | P0       | Medium         | No stable openFDA endpoint confirmed. Use FDA AccessData HTML/download adapter. Docs: https://www.fda.gov/drugs/drug-safety-and-availability/drug-shortages and https://www.accessdata.fda.gov/scripts/drugshortages/default.cfm |
| openFDA Device Registration/Listing | Establishments and devices manufactured at them                                              | Same openFDA limits                                                                                                  | JSON API                                 | Monthly                                          | P0       | Low            | Endpoint: `https://api.fda.gov/device/registrationlisting.json`. Docs: https://open.fda.gov/apis/device/registrationlisting/                                                                                                     |
| openFDA Device Enforcement          | Device recalls/enforcement reports                                                           | Same openFDA limits                                                                                                  | JSON API and feed                        | Weekly                                           | P0       | Low            | Endpoint: `https://api.fda.gov/device/enforcement.json`. Docs: https://open.fda.gov/apis/device/enforcement/                                                                                                                     |
| FDA Warning Letters                 | Warning letters, issuing office, company, subject, issue/post dates, closeout/response links | Public FDA page and downloadable XLSX                                                                                | HTML and XLSX                            | Page-updated, source current as page states      | P1       | Low            | Page includes filtered search and XLSX downloads. Docs/page: https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/compliance-actions-and-activities/warning-letters                                |
| FDA Inspections Data Dashboard      | Final inspection classifications, citations, published 483 references                        | Public dashboard; API credentials may require OII Unified Logon authorization key                                    | HTML/dashboard and downloadable datasets | Weekly                                           | P1       | Medium         | Dashboard documents caveats and dataset downloads. Page: https://datadashboard.fda.gov/oii/cd/inspections.htm                                                                                                                    |
| GDELT 2.0                           | Global news events, mentions, GKG, themes, tone, search signals                              | Public open data, no normal API key for DOC/API examples                                                             | CSV files, BigQuery, API JSON for DOC    | 15-minute streams                                | P0       | Medium         | Use event/GKG file lists for robust ingestion and DOC API for search signals. Docs: https://www.gdeltproject.org/ and https://blog.gdeltproject.org/gdelt-2-0-our-global-world-in-realtime/                                      |
| GDACS                               | Disaster alerts: earthquakes, tropical cyclones, floods, volcanoes, droughts, fires          | Public website and feeds                                                                                             | RSS/HTML/API-like endpoints              | Near real time                                   | P0       | Medium         | Use feeds and event pages first. Docs: https://www.gdacs.org/                                                                                                                                                                    |
| ReliefWeb                           | Humanitarian reports, disasters, updates                                                     | `appname` required; from Nov 1 2025 pre-approved appname required. Quota 1,000 calls/day and 1,000 results/call.     | JSON API                                 | Continuously updated                             | P1       | Low            | API v2. Docs: https://apidoc.reliefweb.int/                                                                                                                                                                                      |
| SEC EDGAR                           | Public company filings, risk factor changes, manufacturing/supplier disclosures              | No API key. Must declare user agent. Fair access rate: 10 requests/sec.                                              | JSON APIs, filing text/HTML, bulk ZIP    | Real-time APIs, nightly bulk ZIP                 | P1       | Medium         | Docs: https://www.sec.gov/search-filings/edgar-application-programming-interfaces and https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data                                                            |
| World Bank Commodity Markets        | Monthly commodity prices and forecasts                                                       | Public data terms                                                                                                    | XLS, PDF, data files                     | Monthly; page gives next update                  | P1       | Low            | "Pink Sheet" monthly and annual price files. Docs: https://www.worldbank.org/en/research/commodity-markets                                                                                                                       |
| EIA Open Data                       | Energy prices, natural gas, petroleum, crude imports, diesel, electricity                    | API registration/key recommended by EIA                                                                              | API, bulk files, Excel add-in            | Daily, weekly, monthly, annual depending dataset | P1       | Low            | Docs: https://www.eia.gov/opendata/                                                                                                                                                                                              |
| UN Comtrade                         | Trade flows by commodity, country, partner, period                                           | Public/commercial tiers and API subscription model may apply                                                         | API/CSV/JSON                             | Monthly/annual by reporting source               | P2       | Medium         | Docs are JS-heavy at https://comtradeplus.un.org/. Implementation should verify exact endpoint and terms before ingestion.                                                                                                       |
| Freight proxies                     | Dry bulk/container rates, shipping and logistics cost indicators                             | Often commercial or delayed through public aggregators                                                               | API/CSV/web pages                        | Daily/weekly                                     | P2       | Medium to High | Prefer official/commercial contracts later. Public proxies can include FRED series, EIA fuel, port congestion data, or licensed freight feeds.                                                                                   |
| Search/trend sources                | Search interest, news volume, query spikes                                                   | API availability and ToS vary                                                                                        | API or exported CSV                      | Daily/hourly                                     | P2       | Medium         | Treat as signals, not facts. Implement generic adapter later after source-specific legal review.                                                                                                                                 |

## openFDA Implementation Details

Official docs confirm:

- API key is free and passed as `api_key`.
- HTTPS requests use `https://api.fda.gov`.
- Query parameters include `search`, `sort`, `count`, `limit`, and `skip`.
- `limit` max is 1000.
- `skip` max is 25000; for larger syncs prefer openFDA downloads.
- Downloads are zipped JSON files. Every endpoint update can change all records, so bulk refreshes must re-download full endpoint files rather than assuming append-only deltas.

Use two ingestion modes:

- API incremental mode for current changes, small searches, and smoke tests.
- Bulk download mode for initial loads and complete refreshes.

Recommended openFDA source configs:

```yaml
source_id: openfda_drug_ndc
adapter: paginated_rest
base_url: https://api.fda.gov/drug/ndc.json
auth:
  type: query_param
  env: OPENFDA_API_KEY
  param: api_key
pagination:
  type: skip_limit
  limit: 1000
  max_skip: 25000
cursor:
  field: listing_expiration_date
  strategy: full_refresh_plus_watermark
dedupe:
  key_fields: [product_ndc]
  content_hash_fields: [raw_payload]
parser_profile: openfda.drug_ndc.v1
cadence: 1d
```

```yaml
source_id: openfda_drug_enforcement
adapter: paginated_rest
base_url: https://api.fda.gov/drug/enforcement.json
auth:
  type: query_param
  env: OPENFDA_API_KEY
  param: api_key
pagination:
  type: skip_limit
  limit: 1000
cursor:
  field: report_date
  strategy: date_window
dedupe:
  key_fields: [recall_number]
parser_profile: openfda.drug_enforcement.v1
cadence: 1d
```

## FDA Shortages Implementation Details

FDA shortage data should start with a web/download adapter:

- Index page: `https://www.accessdata.fda.gov/scripts/drugshortages/default.cfm`
- Download current shortages link is present on the page.
- Detail pages contain presentation-level availability and shortage reasons.
- The FDA page states shortages can occur for manufacturing and quality problems, delays, and discontinuations, and that FDA works with manufacturers to prevent or reduce impact.

Implementation:

- Store index HTML as `raw_documents`.
- Store downloaded shortage file as a separate `raw_document`.
- For each detail page, store raw HTML and extract generic name, active ingredient, status, presentation, company, reason, estimated resupply, update date, and source URL.
- Use content hashes because HTML pages can be corrected in place.
- Mark official `data_license_notes` and `medical_disclaimer`.

## News and Disaster Signals

GDELT:

- Use GDELT event and GKG files for structured data.
- Use DOC API for configurable search terms such as `"drug shortage"`, `"factory fire"`, `"port strike"`, `"FDA warning letter"`, API names, manufacturer names, and facility names.
- Store matched URLs and GDELT metadata as source evidence. Do not treat article claims as verified facts until extraction and evidence verification agents run.

GDACS:

- Ingest disaster event feeds and event detail pages.
- Normalize alert level, event type, location, severity, population/exposure fields when available, start time, update time, and source links.

ReliefWeb:

- Use `https://api.reliefweb.int/v2/reports?appname=<APPNAME>`.
- Use POST for complex filters.
- Use date ranges and `offset` for pagination.
- Filter by themes, countries, disasters, and query terms related to medicines, logistics, manufacturing disruption, health facilities, and humanitarian supply.

## FDA Warning Letters and Inspections

Warning letters:

- Ingest the FDA warning letters page and downloadable XLSX files.
- Extract posted date, letter issue date, company name, issuing office, subject, response letter link, closeout letter link, excerpt, and detail URL.
- Detail pages may include important context and should be stored as raw HTML documents linked to the XLSX row.
- FDA notes that matters described in warning letters may have changed after subsequent interaction with the recipient. Model this as a regulatory signal with temporal caveats, not as a permanent fact.

Inspections dashboard:

- Use downloadable inspections, citations, and published 483 datasets where available.
- The dashboard states datasets are updated weekly and include final actions; it also lists important caveats about missing data, closed status, project areas, and final classifications.
- API access may require an OII Unified Logon authorization key. If unavailable, use documented dataset downloads or manual seed ingestion.
- Extract FEI/facility/company identifiers when present, inspection classification (`NAI`, `VAI`, `OAI`), project area, citation details, inspection date fields, and published 483 links.
- Treat inspection/citation data as regulatory risk evidence with source caveats. Do not overstate facility quality from absence of inspection records.

## Financial, Trade, and Commodity Signals

SEC EDGAR:

- Use `data.sec.gov/submissions/CIK##########.json` for filing history.
- Use company facts APIs for financial data if supplier exposure or segment information becomes useful.
- Download filings using declared user agent and rate limit at or below 10 requests/sec globally.
- Extract risk factors, supply chain sections, manufacturing facilities, shortages, product concentration, vendor concentration, regulatory proceedings, recalls, and disruptions.

World Bank:

- Ingest monthly XLS commodity prices.
- Model each row as `PriceObservation` with commodity, unit, frequency, period, price, currency, and source file.
- Link commodities to `ChemicalInput`, `RawMaterial`, `EnergyInput`, or `TransportRoute` through curated mappings.

EIA:

- Use API and bulk files for petroleum, natural gas, diesel, electricity, coal, and crude import indicators.
- Prioritize daily/weekly prices and fuel inputs relevant to manufacturing and transport costs.

UN Comtrade:

- Defer until endpoint and terms are verified during implementation.
- Target HS codes for active ingredients, excipients, precursors, packaging, medical devices, and raw materials.

## Licensing and Compliance Notes

- openFDA: do not use for medical-care decisions; FDA terms and openFDA responsible-use language apply.
- FDA shortages: official public data, but HTML/download format can change. Maintain parser tests and do not overload pages.
- ReliefWeb: content may be contributed by partners and include copyrighted material. Respect original source rights and use appname.
- SEC EDGAR: declare user agent and follow fair access.
- GDELT: open data but downstream article content belongs to publishers. Store metadata and short evidence spans, not full copyrighted articles unless licensed.
- GDACS: include EU/JRC disclaimers and use alert data responsibly.
- Commercial freight/search/trend sources: require legal approval before production ingestion.

## Initial Source Priority Order

1. `openfda_drug_ndc`
2. `openfda_drug_enforcement`
3. `fda_drug_shortages`
4. `openfda_device_registrationlisting`
5. `openfda_device_enforcement`
6. `fda_warning_letters`
7. `fda_inspections_dashboard`
8. `gdelt_doc_search`
9. `gdacs_events`
10. `reliefweb_reports`
11. `worldbank_commodity_prices`
12. `eia_energy_prices`
13. `sec_edgar_supplier_filings`
14. `un_comtrade_trade_flows`
15. `freight_proxy_prices`
16. `search_trend_signals`
