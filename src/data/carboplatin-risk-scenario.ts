export type RiskLevel = "critical" | "elevated" | "stable" | "watch";

export type GraphNode = {
  detail?: { x: number; y: number };
  id: string;
  kind: "component" | "event" | "medicine" | "place" | "source" | "supplier";
  label: string;
  metric?: string;
  overview: { x: number; y: number };
  risk: RiskLevel;
  summary: string;
};

export type GraphEdge = {
  from: string;
  id: string;
  risk: RiskLevel;
  scripted?: true;
  to: string;
};

export type NodeDetails = Record<
  string,
  {
    confidence: string;
    facts: string[];
    prompts: string[];
    sources: { meta: string; title: string; url: string }[];
    whyItMatters: string;
  }
>;

export const selectedMedicineId = "med-carboplatin";
export const selectedMedicineSlug = "carboplatin-injection";
export const scriptedSourceId = "source-times-india-2026";
export const investigationTargetId = "event-api-shortage-2026";

export const riskPathBase = [
  selectedMedicineId,
  "event-fda-shortage",
  "component-platinum-api",
  "supplier-accord-intas",
  "place-gujarat",
  "event-gmp",
  "source-fda-carboplatin",
  "source-ashp-carboplatin",
];

export const graphNodes: GraphNode[] = [
  {
    detail: { x: 10, y: 50 },
    id: selectedMedicineId,
    kind: "medicine",
    label: "Carboplatin Injection",
    metric: "87",
    overview: { x: 50, y: 50 },
    risk: "critical",
    summary: "Platinum chemotherapy with constrained usable supply across several paths.",
  },
  {
    id: "med-cisplatin",
    kind: "medicine",
    label: "Cisplatin Injection",
    metric: "72",
    overview: { x: 67, y: 38 },
    risk: "elevated",
    summary: "Related platinum chemotherapy with shared upstream exposure.",
  },
  {
    id: "med-oxaliplatin",
    kind: "medicine",
    label: "Oxaliplatin Injection",
    metric: "61",
    overview: { x: 69, y: 60 },
    risk: "elevated",
    summary: "Platinum oncology medicine watched for API pressure signals.",
  },
  {
    id: "med-methotrexate",
    kind: "medicine",
    label: "Methotrexate Injection",
    metric: "49",
    overview: { x: 50, y: 72 },
    risk: "watch",
    summary: "Oncology sterile injectable with separate active ingredient constraints.",
  },
  {
    id: "med-ifosfamide",
    kind: "medicine",
    label: "Ifosfamide Injection",
    metric: "58",
    overview: { x: 31, y: 60 },
    risk: "watch",
    summary: "Recent oncology shortage signal with supplier capacity pressure.",
  },
  {
    id: "med-pemetrexed",
    kind: "medicine",
    label: "Pemetrexed Injection",
    metric: "22",
    overview: { x: 31, y: 38 },
    risk: "stable",
    summary: "Oncology product included as a stable comparator.",
  },
  {
    id: "med-saline",
    kind: "medicine",
    label: "Saline bags",
    metric: "21",
    overview: { x: 50, y: 28 },
    risk: "stable",
    summary: "Infusion supply comparator with broad manufacturing base.",
  },
  {
    detail: { x: 24, y: 50 },
    id: "component-platinum-api",
    kind: "component",
    label: "Platinum-based API",
    metric: "shared",
    overview: { x: 28, y: 24 },
    risk: "critical",
    summary: "Active ingredient layer shared by platinum chemotherapy medicines.",
  },
  {
    detail: { x: 24, y: 72 },
    id: "component-platinum-raw",
    kind: "component",
    label: "Platinum raw material",
    metric: "concentrated",
    overview: { x: 25, y: 77 },
    risk: "elevated",
    summary: "Upstream raw material with concentrated global mining exposure.",
  },
  {
    detail: { x: 24, y: 28 },
    id: "component-sterile-vial",
    kind: "component",
    label: "Sterile injectable vial",
    metric: "capacity",
    overview: { x: 27, y: 50 },
    risk: "watch",
    summary: "Fill-finish capacity determines whether API can become hospital-ready supply.",
  },
  {
    id: "component-oncology-api",
    kind: "component",
    label: "Oncology API capacity",
    overview: { x: 75, y: 74 },
    risk: "watch",
    summary: "Shared active-ingredient capacity watched across sterile oncology medicines.",
  },
  {
    id: "component-glass-vial",
    kind: "component",
    label: "Borosilicate glass",
    overview: { x: 41, y: 18 },
    risk: "stable",
    summary: "Shared sterile container material with broad supplier coverage.",
  },
  {
    id: "component-iv-tubing",
    kind: "component",
    label: "IV tubing resin",
    overview: { x: 37, y: 87 },
    risk: "stable",
    summary: "Commodity input for infusion sets with multiple approved sources.",
  },
  {
    detail: { x: 40, y: 44 },
    id: "supplier-accord-intas",
    kind: "supplier",
    label: "Accord / Intas",
    metric: "GMP",
    overview: { x: 16, y: 34 },
    risk: "critical",
    summary: "Key supplier path with FDA-listed GMP compliance constraint.",
  },
  {
    detail: { x: 40, y: 58 },
    id: "supplier-eugia",
    kind: "supplier",
    label: "Eugia US",
    metric: "demand",
    overview: { x: 15, y: 66 },
    risk: "elevated",
    summary: "FDA lists unavailable presentations tied to demand increase.",
  },
  {
    detail: { x: 40, y: 72 },
    id: "supplier-fresenius",
    kind: "supplier",
    label: "Fresenius Kabi",
    metric: "delay",
    overview: { x: 80, y: 64 },
    risk: "elevated",
    summary: "FDA lists unavailable supply with shipping-delay reason.",
  },
  {
    detail: { x: 40, y: 30 },
    id: "supplier-pfizer",
    kind: "supplier",
    label: "Pfizer / Hospira",
    metric: "limited",
    overview: { x: 90, y: 68 },
    risk: "elevated",
    summary: "FDA lists limited and unavailable presentations due to demand increase.",
  },
  {
    id: "supplier-gland-bpi",
    kind: "supplier",
    label: "Gland / BPI Labs",
    overview: { x: 66, y: 18 },
    risk: "watch",
    summary: "Some carboplatin presentations are discontinued.",
  },
  {
    id: "supplier-teva",
    kind: "supplier",
    label: "Teva",
    overview: { x: 21, y: 92 },
    risk: "watch",
    summary: "Supplier retained in the visible redundancy layer.",
  },
  {
    id: "supplier-apotex",
    kind: "supplier",
    label: "Teyro / Apotex",
    overview: { x: 58, y: 86 },
    risk: "watch",
    summary: "Discontinued presentations reduce practical redundancy.",
  },
  {
    detail: { x: 55, y: 44 },
    id: "place-gujarat",
    kind: "place",
    label: "Gujarat manufacturing site",
    metric: "IN",
    overview: { x: 12, y: 18 },
    risk: "critical",
    summary: "Manufacturing geography tied to the Accord / Intas supply path.",
  },
  {
    detail: { x: 55, y: 72 },
    id: "place-south-africa",
    kind: "place",
    label: "South African platinum supply",
    metric: "raw",
    overview: { x: 12, y: 84 },
    risk: "elevated",
    summary: "Upstream concentration risk for platinum raw material, not a proven direct cause.",
  },
  {
    id: "place-us-oncology",
    kind: "place",
    label: "U.S. oncology market",
    overview: { x: 82, y: 27 },
    risk: "watch",
    summary: "Clinical market where shortages force allocation decisions.",
  },
  {
    id: "place-hospital-pharmacy",
    kind: "place",
    label: "Hospital pharmacy",
    overview: { x: 88, y: 48 },
    risk: "stable",
    summary: "Downstream care setting exposed to upstream availability risk.",
  },
  {
    detail: { x: 70, y: 50 },
    id: "event-fda-shortage",
    kind: "event",
    label: "FDA current shortage",
    metric: "2026",
    overview: { x: 32, y: 12 },
    risk: "critical",
    summary: "FDA lists carboplatin injection as currently in shortage.",
  },
  {
    detail: { x: 70, y: 34 },
    id: "event-gmp",
    kind: "event",
    label: "GMP compliance constraint",
    metric: "quality",
    overview: { x: 84, y: 82 },
    risk: "critical",
    summary: "Manufacturing quality constraint limits a key supplier path.",
  },
  {
    detail: { x: 70, y: 66 },
    id: "event-demand",
    kind: "event",
    label: "Demand increase",
    overview: { x: 91, y: 34 },
    risk: "elevated",
    summary: "FDA lists demand increase across multiple unavailable or limited presentations.",
  },
  {
    detail: { x: 70, y: 78 },
    id: "event-shipping",
    kind: "event",
    label: "Shipping delay",
    overview: { x: 72, y: 88 },
    risk: "elevated",
    summary: "Logistics delay further reduces usable supplier redundancy.",
  },
  {
    id: "event-discontinued",
    kind: "event",
    label: "Discontinued presentations",
    overview: { x: 69, y: 78 },
    risk: "watch",
    summary: "Discontinued products reduce backup supply options.",
  },
  {
    detail: { x: 70, y: 88 },
    id: "event-api-shortage-2026",
    kind: "event",
    label: "2026 API shortage signal",
    metric: "new",
    overview: { x: 46, y: 92 },
    risk: "elevated",
    summary: "News evidence links platinum chemotherapy shortages to API pressure.",
  },
  {
    detail: { x: 70, y: 18 },
    id: "event-platinum-deficit",
    kind: "event",
    label: "Platinum supply deficit",
    overview: { x: 91, y: 88 },
    risk: "watch",
    summary: "Market signal explains upstream fragility without claiming direct causality.",
  },
  {
    detail: { x: 86, y: 38 },
    id: "source-fda-carboplatin",
    kind: "source",
    label: "FDA shortage page",
    metric: "primary",
    overview: { x: 15, y: 8 },
    risk: "critical",
    summary: "Primary source for current shortage and supplier-level constraints.",
  },
  {
    detail: { x: 86, y: 58 },
    id: "source-ashp-carboplatin",
    kind: "source",
    label: "ASHP shortage page",
    metric: "clinical",
    overview: { x: 10, y: 52 },
    risk: "critical",
    summary: "Clinical shortage source for usual-ordering availability.",
  },
  {
    id: "source-axios-2023",
    kind: "source",
    label: "Axios cancer shortage",
    overview: { x: 93, y: 16 },
    risk: "elevated",
    summary: "News context for rationing, delays, and generic oncology fragility.",
  },
  {
    id: "source-health-nccn",
    kind: "source",
    label: "NCCN survey article",
    overview: { x: 74, y: 10 },
    risk: "elevated",
    summary: "Supports oncology-center impact statistics from the 2023 wave.",
  },
  {
    id: "source-ft-intas",
    kind: "source",
    label: "FT Intas analysis",
    overview: { x: 87, y: 24 },
    risk: "elevated",
    summary: "News analysis of Intas / Accord quality failure and market fragility.",
  },
  {
    id: "source-marketwatch-platinum",
    kind: "source",
    label: "Platinum market report",
    overview: { x: 82, y: 92 },
    risk: "watch",
    summary: "Supports the upstream platinum deficit signal.",
  },
  {
    detail: { x: 86, y: 76 },
    id: scriptedSourceId,
    kind: "source",
    label: "Times of India API report",
    metric: "new",
    overview: { x: 18, y: 92 },
    risk: "elevated",
    summary: "Scripted new evidence about 2026 platinum chemotherapy API shortage.",
  },
];

export const graphEdges: GraphEdge[] = [
  {
    from: selectedMedicineId,
    id: "e-carboplatin-shortage",
    risk: "critical",
    to: "event-fda-shortage",
  },
  {
    from: selectedMedicineId,
    id: "e-carboplatin-api",
    risk: "critical",
    to: "component-platinum-api",
  },
  {
    from: selectedMedicineId,
    id: "e-carboplatin-vial",
    risk: "watch",
    to: "component-sterile-vial",
  },
  {
    from: "med-cisplatin",
    id: "e-cisplatin-api",
    risk: "elevated",
    to: "component-platinum-api",
  },
  {
    from: "med-oxaliplatin",
    id: "e-oxaliplatin-api",
    risk: "elevated",
    to: "component-platinum-api",
  },
  {
    from: "med-methotrexate",
    id: "e-methotrexate-oncology-api",
    risk: "watch",
    to: "component-oncology-api",
  },
  {
    from: "med-ifosfamide",
    id: "e-ifosfamide-oncology-api",
    risk: "watch",
    to: "component-oncology-api",
  },
  {
    from: "med-pemetrexed",
    id: "e-pemetrexed-vial",
    risk: "stable",
    to: "component-sterile-vial",
  },
  {
    from: "med-saline",
    id: "e-saline-vial",
    risk: "stable",
    to: "component-sterile-vial",
  },
  {
    from: "component-platinum-api",
    id: "e-api-accord-intas",
    risk: "critical",
    to: "supplier-accord-intas",
  },
  {
    from: "component-platinum-api",
    id: "e-api-eugia",
    risk: "elevated",
    to: "supplier-eugia",
  },
  {
    from: "component-platinum-api",
    id: "e-api-fresenius",
    risk: "elevated",
    to: "supplier-fresenius",
  },
  {
    from: "component-platinum-api",
    id: "e-api-pfizer",
    risk: "elevated",
    to: "supplier-pfizer",
  },
  {
    from: "component-platinum-api",
    id: "e-api-gland-bpi",
    risk: "watch",
    to: "supplier-gland-bpi",
  },
  {
    from: "component-platinum-api",
    id: "e-api-teva",
    risk: "watch",
    to: "supplier-teva",
  },
  {
    from: "component-platinum-api",
    id: "e-api-apotex",
    risk: "watch",
    to: "supplier-apotex",
  },
  {
    from: "component-platinum-api",
    id: "e-api-raw-platinum",
    risk: "elevated",
    to: "component-platinum-raw",
  },
  {
    from: "component-sterile-vial",
    id: "e-vial-pfizer",
    risk: "watch",
    to: "supplier-pfizer",
  },
  {
    from: "component-sterile-vial",
    id: "e-vial-glass",
    risk: "stable",
    to: "component-glass-vial",
  },
  {
    from: "supplier-accord-intas",
    id: "e-accord-gujarat",
    risk: "critical",
    to: "place-gujarat",
  },
  {
    from: "supplier-accord-intas",
    id: "e-accord-gmp",
    risk: "critical",
    to: "event-gmp",
  },
  {
    from: "supplier-eugia",
    id: "e-eugia-demand",
    risk: "elevated",
    to: "event-demand",
  },
  {
    from: "supplier-fresenius",
    id: "e-fresenius-shipping",
    risk: "elevated",
    to: "event-shipping",
  },
  {
    from: "supplier-pfizer",
    id: "e-pfizer-demand",
    risk: "elevated",
    to: "event-demand",
  },
  {
    from: "supplier-apotex",
    id: "e-apotex-discontinued",
    risk: "watch",
    to: "event-discontinued",
  },
  {
    from: "component-platinum-raw",
    id: "e-raw-south-africa",
    risk: "elevated",
    to: "place-south-africa",
  },
  {
    from: "place-south-africa",
    id: "e-south-africa-deficit",
    risk: "watch",
    to: "event-platinum-deficit",
  },
  {
    from: "event-fda-shortage",
    id: "e-shortage-fda-source",
    risk: "critical",
    to: "source-fda-carboplatin",
  },
  {
    from: "event-fda-shortage",
    id: "e-shortage-ashp-source",
    risk: "critical",
    to: "source-ashp-carboplatin",
  },
  {
    from: "event-gmp",
    id: "e-gmp-ft-source",
    risk: "elevated",
    to: "source-ft-intas",
  },
  {
    from: "place-us-oncology",
    id: "e-us-oncology-axios",
    risk: "elevated",
    to: "source-axios-2023",
  },
  {
    from: "place-us-oncology",
    id: "e-us-oncology-nccn",
    risk: "elevated",
    to: "source-health-nccn",
  },
  {
    from: "event-platinum-deficit",
    id: "e-platinum-marketwatch",
    risk: "watch",
    to: "source-marketwatch-platinum",
  },
  {
    from: "event-api-shortage-2026",
    id: "e-api-shortage-times-india",
    risk: "elevated",
    scripted: true,
    to: scriptedSourceId,
  },
  {
    from: "component-platinum-api",
    id: "e-api-shortage-signal",
    risk: "elevated",
    scripted: true,
    to: "event-api-shortage-2026",
  },
];

export const medicineSupplyChainEdges: Record<string, string[]> = {
  [selectedMedicineId]: [
    "e-carboplatin-shortage",
    "e-carboplatin-api",
    "e-carboplatin-vial",
    "e-api-accord-intas",
    "e-accord-gujarat",
    "e-accord-gmp",
    "e-shortage-fda-source",
    "e-shortage-ashp-source",
    "e-api-eugia",
    "e-eugia-demand",
    "e-api-fresenius",
    "e-fresenius-shipping",
    "e-api-pfizer",
    "e-pfizer-demand",
    "e-api-apotex",
    "e-apotex-discontinued",
    "e-api-raw-platinum",
    "e-raw-south-africa",
    "e-south-africa-deficit",
    "e-platinum-marketwatch",
  ],
  "med-cisplatin": [
    "e-cisplatin-api",
    "e-api-accord-intas",
    "e-accord-gujarat",
    "e-accord-gmp",
    "e-gmp-ft-source",
    "e-api-raw-platinum",
    "e-raw-south-africa",
  ],
  "med-oxaliplatin": [
    "e-oxaliplatin-api",
    "e-api-raw-platinum",
    "e-raw-south-africa",
    "e-south-africa-deficit",
  ],
  "med-methotrexate": ["e-methotrexate-oncology-api"],
  "med-ifosfamide": ["e-ifosfamide-oncology-api"],
  "med-pemetrexed": ["e-pemetrexed-vial"],
  "med-saline": ["e-saline-vial", "e-vial-glass"],
};

const primarySources = [
  {
    meta: "FDA, current shortage",
    title: "Carboplatin Injection Shortage",
    url: "https://www.accessdata.fda.gov/scripts/drugshortages/dsp_ActiveIngredientDetails.cfm?AI=Carboplatin+Injection&st=c&tab=tabs-1",
  },
  {
    meta: "ASHP, clinical shortage detail",
    title: "Carboplatin Injection Shortage",
    url: "https://www.ashp.org/drug-shortages/current-shortages/drug-shortage-detail.aspx?id=930",
  },
  {
    meta: "News, May 2026",
    title: "W Asia conflict, API shortage choke platinum-based chemo drugs' supply",
    url: "https://timesofindia.indiatimes.com/city/ahmedabad/w-asia-conflict-api-shortage-choke-platinum-based-chemo-drugs-supply/articleshow/130837958.cms",
  },
  {
    meta: "News context, June 2023",
    title: "Cancer drug shortages expose supply chain vulnerabilities",
    url: "https://www.axios.com/2023/06/14/cancer-drug-shortages-supply-chain-vulnerabilities",
  },
];

export const nodeDetails: NodeDetails = {
  [selectedMedicineId]: {
    confidence: "High confidence, 4 Evidence Sources",
    facts: [
      "Supply fragility: high",
      "Multiple listed suppliers, constrained usable supply",
      "Evidence strength: high",
      "Patient story is narrative only; no patient node is modeled",
    ],
    prompts: [
      "Find newer evidence",
      "Explain risk path",
      "Check demand pressure",
      "Review alternate supplier readiness",
    ],
    sources: primarySources,
    whyItMatters:
      "Carboplatin is a platinum chemotherapy medicine where delayed availability can force oncology teams to ration, delay, or substitute treatment.",
  },
  "event-fda-shortage": {
    confidence: "Primary evidence",
    facts: [
      "FDA lists Carboplatin Injection as currently in shortage",
      "Supplier rows include GMP compliance, demand increase, shipping delay, and discontinuations",
      "This is the hard evidence anchor for the risk path",
    ],
    prompts: ["Find newer evidence", "Explain risk path"],
    sources: primarySources.slice(0, 2),
    whyItMatters:
      "The FDA and ASHP shortage records turn the graph from a hypothesis into a sourced availability signal.",
  },
  "component-platinum-api": {
    confidence: "High contribution",
    facts: [
      "Active ingredient layer connects carboplatin, cisplatin, and oxaliplatin",
      "API pressure is a supply-chain risk amplifier",
      "The graph separates API risk from patient data",
    ],
    prompts: ["Find newer evidence", "Review alternate supplier readiness"],
    sources: [primarySources[0], primarySources[2]],
    whyItMatters:
      "The API is the upstream component that explains why supplier problems can propagate into hospital-ready chemotherapy supply.",
  },
  "supplier-accord-intas": {
    confidence: "Critical supplier path",
    facts: [
      "FDA lists Accord presentations as unavailable for GMP compliance requirements",
      "The supplier connects the medicine to a manufacturing quality risk",
      "Other listed suppliers do not fully remove the availability risk",
    ],
    prompts: ["Explain risk path", "Review alternate supplier readiness"],
    sources: [primarySources[0]],
    whyItMatters:
      "Accord / Intas is the visible supplier path where a quality event becomes operational supply risk.",
  },
  "place-gujarat": {
    confidence: "High place relevance",
    facts: [
      "Manufacturing geography tied to the supplier path",
      "Place node is a graph location, not a patient location",
      "Useful for explaining concentration risk",
    ],
    prompts: ["Explain risk path"],
    sources: [primarySources[0]],
    whyItMatters:
      "The place node shows where supplier exposure becomes a real-world manufacturing dependency.",
  },
  "event-gmp": {
    confidence: "Primary evidence",
    facts: [
      "FDA-listed reason: requirements related to complying with good manufacturing practices",
      "Quality constraints can remove capacity even when demand is unchanged",
      "This is the main red event in the supplier branch",
    ],
    prompts: ["Explain risk path", "Review alternate supplier readiness"],
    sources: [primarySources[0]],
    whyItMatters:
      "The GMP event explains why a named supplier path is not equivalent to usable supply.",
  },
  "event-demand": {
    confidence: "Primary evidence",
    facts: [
      "FDA lists demand increase as a reason for limited or unavailable supplier presentations",
      "Demand pressure compounds the quality event",
      "This is a supplier-specific event, not a broad patient-demand node",
    ],
    prompts: ["Check demand pressure", "Explain risk path"],
    sources: [primarySources[0]],
    whyItMatters:
      "Demand increase matters because backup suppliers may already be absorbing redirected orders.",
  },
  "event-shipping": {
    confidence: "Primary evidence",
    facts: [
      "FDA lists shipping delay for a supplier path",
      "Logistics delays reduce usable redundancy",
      "This branch should stay elevated, not critical",
    ],
    prompts: ["Explain risk path"],
    sources: [primarySources[0]],
    whyItMatters:
      "Shipping delay turns nominal supply into uncertain delivery timing for hospital buyers.",
  },
  "component-platinum-raw": {
    confidence: "Risk signal, not direct cause",
    facts: [
      "Platinum raw material is upstream of platinum chemotherapy",
      "South Africa is a major concentration point for platinum supply",
      "This branch is an upstream risk amplifier, not the proven shortage cause",
    ],
    prompts: ["Find newer evidence", "Explain risk path"],
    sources: [
      {
        meta: "Market context",
        title: "Why platinum prices continue to lose luster despite a supply shortage",
        url: "https://www.marketwatch.com/story/why-platinum-prices-continue-to-lose-luster-despite-a-supply-shortage-72029047",
      },
    ],
    whyItMatters:
      "Raw material concentration helps explain fragility without overstating causality for the current shortage.",
  },
  "place-south-africa": {
    confidence: "Elevated upstream watch",
    facts: [
      "Upstream concentration risk for platinum supply",
      "Do not present as a proven direct cause of the FDA carboplatin shortage",
      "Useful for showing why Sanitas distinguishes evidence from risk signals",
    ],
    prompts: ["Find newer evidence", "Explain risk path"],
    sources: [
      {
        meta: "Market context",
        title: "Why platinum prices continue to lose luster despite a supply shortage",
        url: "https://www.marketwatch.com/story/why-platinum-prices-continue-to-lose-luster-despite-a-supply-shortage-72029047",
      },
    ],
    whyItMatters:
      "The place node helps users see broader upstream concentration while keeping the direct shortage path anchored in FDA data.",
  },
  "event-api-shortage-2026": {
    confidence: "New evidence candidate",
    facts: [
      "May 2026 report links platinum chemotherapy availability to API shortages",
      "Strengthens upstream explanation",
      "Risk confidence increases modestly because this is news evidence",
    ],
    prompts: ["Explain risk path", "Review alternate supplier readiness"],
    sources: [primarySources[2]],
    whyItMatters:
      "The newer source gives the scripted investigation a current 2026 reason to expand the graph upstream.",
  },
  "source-fda-carboplatin": {
    confidence: "Primary Evidence Satellite",
    facts: [
      "Supports current shortage status",
      "Supports supplier-specific reasons",
      "Opened deliberately from the panel",
    ],
    prompts: ["Find newer evidence"],
    sources: [primarySources[0]],
    whyItMatters:
      "This Evidence Satellite is the main proof point for the focused shortage signal.",
  },
  "source-ashp-carboplatin": {
    confidence: "Clinical Evidence Satellite",
    facts: [
      "Supports insufficient usual ordering",
      "Clinical pharmacy context",
      "Opened deliberately from the panel",
    ],
    prompts: ["Find newer evidence"],
    sources: [primarySources[1]],
    whyItMatters:
      "This Evidence Satellite explains why the shortage matters to hospital pharmacy teams.",
  },
  "source-axios-2023": {
    confidence: "News context",
    facts: [
      "Explains oncology rationing and delay context",
      "Historical background, not the current shortage anchor",
    ],
    prompts: ["Explain risk path"],
    sources: [primarySources[3]],
    whyItMatters: "This source provides context for why oncology shortages matter operationally.",
  },
  "source-health-nccn": {
    confidence: "Survey context",
    facts: [
      "Supports oncology-center impact statistics",
      "Historical context for platinum chemotherapy shortage wave",
    ],
    prompts: ["Explain risk path"],
    sources: [
      {
        meta: "Survey reporting",
        title: "Chemotherapy Drug Shortage",
        url: "https://www.health.com/chemotherapy-drug-shortage-7547746",
      },
    ],
    whyItMatters:
      "This source backs the care-impact narrative without adding patient nodes to the graph.",
  },
  "source-ft-intas": {
    confidence: "News analysis",
    facts: [
      "Supports the Intas / Accord manufacturing-quality context",
      "Use as context alongside FDA primary shortage data",
    ],
    prompts: ["Explain risk path"],
    sources: [
      {
        meta: "News analysis",
        title: "US cancer drug shortages force doctors to ration life-saving treatments",
        url: "https://www.ft.com/content/6143300d-d11a-4b2f-898c-87c5dd0ff6ce",
      },
    ],
    whyItMatters:
      "This source helps explain how a manufacturing-quality failure can ripple into cancer-drug availability.",
  },
  "source-marketwatch-platinum": {
    confidence: "Upstream risk signal",
    facts: [
      "Supports platinum-market pressure",
      "Risk amplifier only, not direct shortage causality",
    ],
    prompts: ["Find newer evidence"],
    sources: [
      {
        meta: "Market context",
        title: "Why platinum prices continue to lose luster despite a supply shortage",
        url: "https://www.marketwatch.com/story/why-platinum-prices-continue-to-lose-luster-despite-a-supply-shortage-72029047",
      },
    ],
    whyItMatters:
      "This Evidence Satellite shows how upstream market signals can be represented without overstating certainty.",
  },
  [scriptedSourceId]: {
    confidence: "New evidence added",
    facts: [
      "Added by scripted Graph Investigation",
      "Evidence only",
      "Risk confidence increased modestly",
    ],
    prompts: ["Explain risk path", "Review alternate supplier readiness"],
    sources: [primarySources[2]],
    whyItMatters:
      "The new evidence strengthens the upstream API-risk explanation without changing the proven supplier chain.",
  },
};
