export type RiskLevel = "critical" | "elevated" | "stable" | "watch";

export type GraphNode = {
  actionPath?: true;
  detail?: { x: number; y: number };
  id: string;
  kind: "component" | "event" | "medicine" | "place" | "source" | "supplier";
  label: string;
  metric?: string;
  overview: { x: number; y: number };
  risk: RiskLevel;
  riskReason?: string;
  riskScore?: number;
  summary: string;
};

export type GraphEdge = {
  actionPath?: true;
  from: string;
  id: string;
  risk: RiskLevel;
  riskScore?: number;
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

export type SupplyRiskReportPreview = {
  actionPathNodeIds: string[];
  caveats: string[];
  confidence: {
    label: string;
    rationale: string;
  };
  evidenceSourceNodeIds: string[];
  generatedAtLabel: string;
  headlineFinding: string;
  id: string;
  medicineId: string;
  pdfUrl: string;
  recommendedAction: {
    checklist: string[];
    summary: string;
    title: string;
  };
  status: "action-needed" | "stable" | "watch";
  title: string;
};

export const selectedMedicineId = "med-carboplatin";
export const selectedMedicineSlug = "carboplatin-injection";
export const scriptedSourceId = "source-times-india-2026";
export const investigationTargetId = "event-api-shortage-2026";

export const riskPathBase = [
  selectedMedicineId,
  "event-fda-shortage",
  "supplier-accord-intas",
  "event-gmp",
];

export const supplierRiskPath = [selectedMedicineId, "supplier-accord-intas", "event-gmp"];

export const carboplatinReportPreview: SupplyRiskReportPreview = {
  actionPathNodeIds: supplierRiskPath,
  caveats: [
    "Patient impact is narration only and not represented as patient-level data.",
    "Upstream platinum and API signals are risk amplifiers, not the direct proven cause.",
  ],
  confidence: {
    label: "High",
    rationale:
      "Current shortage evidence is backed by primary shortage sources; API evidence is supporting context.",
  },
  evidenceSourceNodeIds: ["source-fda-carboplatin", "source-ashp-carboplatin", scriptedSourceId],
  generatedAtLabel: "Prepared from mapped evidence",
  headlineFinding:
    "Active shortage evidence and a supplier quality constraint create a high-risk path for hospital-ready carboplatin supply.",
  id: "report-carboplatin-demo",
  medicineId: selectedMedicineId,
  pdfUrl: "/reports/carboplatin-supply-risk-brief.pdf",
  recommendedAction: {
    checklist: [
      "Check approved alternatives",
      "Confirm lead times",
      "Review current stock and safety threshold",
      "Escalate oncology allocation policy only if inventory drops",
    ],
    summary:
      "Verify approved supplier availability and lead time before stock falls below safety threshold.",
    title: "Prepare alternate supplier order",
  },
  status: "action-needed",
  title: "Carboplatin Injection Supply Risk Brief",
};

export const graphNodes: GraphNode[] = [
  {
    actionPath: true,
    detail: { x: 10, y: 50 },
    id: selectedMedicineId,
    kind: "medicine",
    label: "Carboplatin Injection",
    metric: "87",
    overview: { x: 50, y: 50 },
    risk: "critical",
    riskReason: "Official shortage evidence plus one clearly constrained supplier path.",
    riskScore: 87,
    summary: "Platinum chemotherapy with constrained usable supply across several paths.",
  },
  {
    id: "med-cisplatin",
    kind: "medicine",
    label: "Cisplatin Injection",
    metric: "72",
    overview: { x: 67, y: 38 },
    risk: "elevated",
    riskScore: 62,
    summary: "Related platinum chemotherapy with shared upstream exposure.",
  },
  {
    id: "med-oxaliplatin",
    kind: "medicine",
    label: "Oxaliplatin Injection",
    metric: "61",
    overview: { x: 69, y: 60 },
    risk: "elevated",
    riskScore: 54,
    summary: "Platinum oncology medicine watched for API pressure signals.",
  },
  {
    id: "med-methotrexate",
    kind: "medicine",
    label: "Methotrexate Injection",
    metric: "49",
    overview: { x: 50, y: 72 },
    risk: "watch",
    riskScore: 41,
    summary: "Oncology sterile injectable with separate active ingredient constraints.",
  },
  {
    id: "med-ifosfamide",
    kind: "medicine",
    label: "Ifosfamide Injection",
    metric: "58",
    overview: { x: 31, y: 60 },
    risk: "watch",
    riskScore: 47,
    summary: "Recent oncology shortage signal with supplier capacity pressure.",
  },
  {
    id: "med-pemetrexed",
    kind: "medicine",
    label: "Pemetrexed Injection",
    metric: "22",
    overview: { x: 31, y: 38 },
    risk: "stable",
    riskScore: 22,
    summary: "Oncology product included as a stable comparator.",
  },
  {
    id: "med-saline",
    kind: "medicine",
    label: "Saline bags",
    metric: "21",
    overview: { x: 50, y: 28 },
    risk: "stable",
    riskScore: 21,
    summary: "Infusion supply comparator with broad manufacturing base.",
  },
  {
    detail: { x: 24, y: 50 },
    id: "component-platinum-api",
    kind: "component",
    label: "Platinum-based API",
    metric: "shared",
    overview: { x: 28, y: 24 },
    risk: "elevated",
    riskReason: "Contextual API pressure signal, useful but not the main action path.",
    riskScore: 64,
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
    riskScore: 52,
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
    riskScore: 38,
    summary: "Fill-finish capacity determines whether API can become hospital-ready supply.",
  },
  {
    id: "component-oncology-api",
    kind: "component",
    label: "Oncology API capacity",
    overview: { x: 75, y: 74 },
    risk: "watch",
    riskScore: 36,
    summary: "Shared active-ingredient capacity watched across sterile oncology medicines.",
  },
  {
    id: "component-glass-vial",
    kind: "component",
    label: "Borosilicate glass",
    overview: { x: 41, y: 18 },
    risk: "stable",
    riskScore: 18,
    summary: "Shared sterile container material with broad supplier coverage.",
  },
  {
    id: "component-iv-tubing",
    kind: "component",
    label: "IV tubing resin",
    overview: { x: 37, y: 87 },
    risk: "stable",
    riskScore: 15,
    summary: "Commodity input for infusion sets with multiple approved sources.",
  },
  {
    actionPath: true,
    detail: { x: 40, y: 44 },
    id: "supplier-accord-intas",
    kind: "supplier",
    label: "Accord / Intas",
    metric: "GMP",
    overview: { x: 16, y: 34 },
    risk: "critical",
    riskReason: "FDA lists Accord presentations unavailable for GMP compliance requirements.",
    riskScore: 92,
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
    riskReason: "Context supplier: FDA lists unavailable presentations tied to demand increase.",
    riskScore: 68,
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
    riskReason: "Context supplier: shipping delay reduces usable redundancy.",
    riskScore: 61,
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
    riskReason: "Context supplier: limited and unavailable presentations due to demand.",
    riskScore: 64,
    summary: "FDA lists limited and unavailable presentations due to demand increase.",
  },
  {
    id: "supplier-gland-bpi",
    kind: "supplier",
    label: "Gland / BPI Labs",
    overview: { x: 66, y: 18 },
    risk: "watch",
    riskReason: "Context supplier: discontinued presentations narrow fallback capacity.",
    riskScore: 44,
    summary: "Some carboplatin presentations are discontinued.",
  },
  {
    id: "supplier-teva",
    kind: "supplier",
    label: "Teva",
    overview: { x: 21, y: 92 },
    risk: "watch",
    riskReason: "Visible supplier retained as lower-active-risk redundancy context.",
    riskScore: 30,
    summary: "Supplier retained in the visible redundancy layer.",
  },
  {
    id: "supplier-apotex",
    kind: "supplier",
    label: "Teyro / Apotex",
    overview: { x: 58, y: 86 },
    risk: "watch",
    riskReason: "Context supplier: discontinued presentations reduce backup supply options.",
    riskScore: 42,
    summary: "Discontinued presentations reduce practical redundancy.",
  },
  {
    detail: { x: 55, y: 44 },
    id: "place-gujarat",
    kind: "place",
    label: "Gujarat manufacturing site",
    metric: "IN",
    overview: { x: 12, y: 18 },
    risk: "watch",
    riskScore: 46,
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
    riskScore: 50,
    summary: "Upstream concentration risk for platinum raw material, not a proven direct cause.",
  },
  {
    id: "place-us-oncology",
    kind: "place",
    label: "U.S. oncology market",
    overview: { x: 82, y: 27 },
    risk: "watch",
    riskScore: 39,
    summary: "Clinical market where shortages force allocation decisions.",
  },
  {
    id: "place-hospital-pharmacy",
    kind: "place",
    label: "Hospital pharmacy",
    overview: { x: 88, y: 48 },
    risk: "stable",
    riskScore: 24,
    summary: "Downstream care setting exposed to upstream availability risk.",
  },
  {
    actionPath: true,
    detail: { x: 70, y: 50 },
    id: "event-fda-shortage",
    kind: "event",
    label: "FDA current shortage",
    metric: "2026",
    overview: { x: 32, y: 12 },
    risk: "critical",
    riskReason: "Primary FDA evidence confirms the active carboplatin shortage.",
    riskScore: 90,
    summary: "FDA lists carboplatin injection as currently in shortage.",
  },
  {
    actionPath: true,
    detail: { x: 70, y: 34 },
    id: "event-gmp",
    kind: "event",
    label: "GMP compliance constraint",
    metric: "quality",
    overview: { x: 84, y: 82 },
    risk: "critical",
    riskReason: "The clearest actionable constraint: quality compliance limits a supplier path.",
    riskScore: 94,
    summary: "Manufacturing quality constraint limits a key supplier path.",
  },
  {
    detail: { x: 70, y: 66 },
    id: "event-demand",
    kind: "event",
    label: "Demand increase",
    overview: { x: 91, y: 34 },
    risk: "elevated",
    riskScore: 63,
    summary: "FDA lists demand increase across multiple unavailable or limited presentations.",
  },
  {
    detail: { x: 70, y: 78 },
    id: "event-shipping",
    kind: "event",
    label: "Shipping delay",
    overview: { x: 72, y: 88 },
    risk: "elevated",
    riskScore: 59,
    summary: "Logistics delay further reduces usable supplier redundancy.",
  },
  {
    id: "event-discontinued",
    kind: "event",
    label: "Discontinued presentations",
    overview: { x: 69, y: 78 },
    risk: "watch",
    riskScore: 43,
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
    riskReason: "Supporting source found by investigation, not a second urgent action path.",
    riskScore: 57,
    summary: "News evidence links platinum chemotherapy shortages to API pressure.",
  },
  {
    detail: { x: 70, y: 18 },
    id: "event-platinum-deficit",
    kind: "event",
    label: "Platinum supply deficit",
    overview: { x: 91, y: 88 },
    risk: "watch",
    riskScore: 37,
    summary: "Market signal explains upstream fragility without claiming direct causality.",
  },
  {
    id: "source-fda-cisplatin",
    kind: "source",
    label: "FDA cisplatin shortage",
    metric: "primary",
    overview: { x: 77, y: 4 },
    risk: "stable",
    riskScore: 20,
    summary: "Primary source for related platinum chemotherapy shortage status.",
  },
  {
    id: "source-fda-oxaliplatin",
    kind: "source",
    label: "FDA oxaliplatin listing",
    metric: "primary",
    overview: { x: 95, y: 57 },
    risk: "stable",
    riskScore: 18,
    summary: "Primary shortage database signal for related platinum chemotherapy context.",
  },
  {
    id: "source-ashp-oncology",
    kind: "source",
    label: "ASHP oncology listings",
    metric: "clinical",
    overview: { x: 61, y: 96 },
    risk: "stable",
    riskScore: 19,
    summary: "Clinical pharmacy shortage listings for oncology sterile injectables.",
  },
  {
    detail: { x: 86, y: 24 },
    id: "source-fda-sterile-injectables",
    kind: "source",
    label: "Guardian injectable shortage",
    metric: "news",
    overview: { x: 35, y: 6 },
    risk: "stable",
    riskScore: 18,
    summary: "News analysis of generic sterile injectable manufacturing fragility.",
  },
  {
    detail: { x: 86, y: 38 },
    id: "source-fda-carboplatin",
    kind: "source",
    label: "FDA shortage page",
    metric: "primary",
    overview: { x: 15, y: 8 },
    risk: "stable",
    riskScore: 20,
    summary: "Primary source for current shortage and supplier-level constraints.",
  },
  {
    detail: { x: 86, y: 58 },
    id: "source-ashp-carboplatin",
    kind: "source",
    label: "ASHP shortage page",
    metric: "clinical",
    overview: { x: 10, y: 52 },
    risk: "stable",
    riskScore: 20,
    summary: "Clinical shortage source for usual-ordering availability.",
  },
  {
    id: "source-axios-2023",
    kind: "source",
    label: "Axios cancer shortage",
    overview: { x: 93, y: 16 },
    risk: "stable",
    riskScore: 18,
    summary: "News context for rationing, delays, and generic oncology fragility.",
  },
  {
    id: "source-health-nccn",
    kind: "source",
    label: "NCCN survey article",
    overview: { x: 74, y: 10 },
    risk: "stable",
    riskScore: 18,
    summary: "Supports oncology-center impact statistics from the 2023 wave.",
  },
  {
    id: "source-ft-intas",
    kind: "source",
    label: "FT Intas analysis",
    overview: { x: 87, y: 24 },
    risk: "stable",
    riskScore: 18,
    summary: "News analysis of Intas / Accord quality failure and market fragility.",
  },
  {
    id: "source-marketwatch-platinum",
    kind: "source",
    label: "WPIC platinum deficit",
    overview: { x: 82, y: 92 },
    risk: "stable",
    riskScore: 18,
    summary: "Industry market evidence for platinum deficit and concentration risk.",
  },
  {
    detail: { x: 86, y: 76 },
    id: scriptedSourceId,
    kind: "source",
    label: "Times of India API report",
    metric: "new",
    overview: { x: 18, y: 92 },
    risk: "stable",
    riskReason: "New evidence supports the report context without changing the action path.",
    riskScore: 20,
    summary: "Scripted new evidence about 2026 platinum chemotherapy API shortage.",
  },
];

export const graphEdges: GraphEdge[] = [
  {
    from: selectedMedicineId,
    id: "e-carboplatin-fda-source",
    risk: "critical",
    riskScore: 82,
    to: "source-fda-carboplatin",
  },
  {
    actionPath: true,
    from: selectedMedicineId,
    id: "e-carboplatin-shortage",
    risk: "critical",
    riskScore: 90,
    to: "event-fda-shortage",
  },
  {
    actionPath: true,
    from: "event-fda-shortage",
    id: "e-shortage-accord",
    risk: "critical",
    riskScore: 88,
    to: "supplier-accord-intas",
  },
  {
    from: selectedMedicineId,
    id: "e-carboplatin-api",
    risk: "elevated",
    riskScore: 64,
    to: "component-platinum-api",
  },
  {
    from: selectedMedicineId,
    id: "e-carboplatin-vial",
    risk: "watch",
    riskScore: 38,
    to: "component-sterile-vial",
  },
  {
    from: "med-cisplatin",
    id: "e-cisplatin-api",
    risk: "elevated",
    riskScore: 62,
    to: "component-platinum-api",
  },
  {
    from: "med-cisplatin",
    id: "e-cisplatin-fda-source",
    risk: "elevated",
    riskScore: 62,
    to: "source-fda-cisplatin",
  },
  {
    from: "med-oxaliplatin",
    id: "e-oxaliplatin-api",
    risk: "elevated",
    riskScore: 54,
    to: "component-platinum-api",
  },
  {
    from: "med-oxaliplatin",
    id: "e-oxaliplatin-fda-source",
    risk: "elevated",
    riskScore: 54,
    to: "source-fda-oxaliplatin",
  },
  {
    from: "med-methotrexate",
    id: "e-methotrexate-oncology-api",
    risk: "watch",
    riskScore: 41,
    to: "component-oncology-api",
  },
  {
    from: "med-methotrexate",
    id: "e-methotrexate-ashp-source",
    risk: "watch",
    riskScore: 41,
    to: "source-ashp-oncology",
  },
  {
    from: "med-ifosfamide",
    id: "e-ifosfamide-oncology-api",
    risk: "watch",
    riskScore: 47,
    to: "component-oncology-api",
  },
  {
    from: "med-ifosfamide",
    id: "e-ifosfamide-ashp-source",
    risk: "watch",
    riskScore: 47,
    to: "source-ashp-oncology",
  },
  {
    from: "med-pemetrexed",
    id: "e-pemetrexed-vial",
    risk: "stable",
    riskScore: 22,
    to: "component-sterile-vial",
  },
  {
    from: "med-saline",
    id: "e-saline-vial",
    risk: "stable",
    riskScore: 21,
    to: "component-sterile-vial",
  },
  {
    from: "component-platinum-api",
    id: "e-api-accord-intas",
    risk: "elevated",
    riskScore: 66,
    to: "supplier-accord-intas",
  },
  {
    from: "component-platinum-api",
    id: "e-api-times-india-source",
    risk: "elevated",
    riskScore: 57,
    to: scriptedSourceId,
  },
  {
    from: "component-platinum-api",
    id: "e-api-eugia",
    risk: "elevated",
    riskScore: 58,
    to: "supplier-eugia",
  },
  {
    from: "component-platinum-api",
    id: "e-api-fresenius",
    risk: "elevated",
    riskScore: 55,
    to: "supplier-fresenius",
  },
  {
    from: "component-platinum-api",
    id: "e-api-pfizer",
    risk: "elevated",
    riskScore: 57,
    to: "supplier-pfizer",
  },
  {
    from: "component-platinum-api",
    id: "e-api-gland-bpi",
    risk: "watch",
    riskScore: 43,
    to: "supplier-gland-bpi",
  },
  {
    from: "component-platinum-api",
    id: "e-api-teva",
    risk: "watch",
    riskScore: 30,
    to: "supplier-teva",
  },
  {
    from: "component-platinum-api",
    id: "e-api-apotex",
    risk: "watch",
    riskScore: 42,
    to: "supplier-apotex",
  },
  {
    from: "component-platinum-api",
    id: "e-api-raw-platinum",
    risk: "elevated",
    riskScore: 50,
    to: "component-platinum-raw",
  },
  {
    from: "component-sterile-vial",
    id: "e-vial-pfizer",
    risk: "watch",
    riskScore: 38,
    to: "supplier-pfizer",
  },
  {
    from: "component-sterile-vial",
    id: "e-vial-fda-source",
    risk: "watch",
    riskScore: 38,
    to: "source-fda-sterile-injectables",
  },
  {
    from: "component-oncology-api",
    id: "e-oncology-api-ashp-source",
    risk: "watch",
    riskScore: 36,
    to: "source-ashp-oncology",
  },
  {
    from: "component-sterile-vial",
    id: "e-vial-glass",
    risk: "stable",
    riskScore: 18,
    to: "component-glass-vial",
  },
  {
    from: "supplier-accord-intas",
    id: "e-accord-fda-source",
    risk: "critical",
    riskScore: 82,
    to: "source-fda-carboplatin",
  },
  {
    from: "supplier-accord-intas",
    id: "e-accord-gujarat",
    risk: "watch",
    riskScore: 46,
    to: "place-gujarat",
  },
  {
    actionPath: true,
    from: "supplier-accord-intas",
    id: "e-accord-gmp",
    risk: "critical",
    riskScore: 94,
    to: "event-gmp",
  },
  {
    from: "supplier-eugia",
    id: "e-eugia-fda-source",
    risk: "elevated",
    riskScore: 68,
    to: "source-fda-carboplatin",
  },
  {
    from: "supplier-eugia",
    id: "e-eugia-demand",
    risk: "elevated",
    riskScore: 63,
    to: "event-demand",
  },
  {
    from: "supplier-fresenius",
    id: "e-fresenius-fda-source",
    risk: "elevated",
    riskScore: 61,
    to: "source-fda-carboplatin",
  },
  {
    from: "supplier-fresenius",
    id: "e-fresenius-shipping",
    risk: "elevated",
    riskScore: 59,
    to: "event-shipping",
  },
  {
    from: "supplier-pfizer",
    id: "e-pfizer-fda-source",
    risk: "elevated",
    riskScore: 64,
    to: "source-fda-carboplatin",
  },
  {
    from: "supplier-pfizer",
    id: "e-pfizer-demand",
    risk: "elevated",
    riskScore: 64,
    to: "event-demand",
  },
  {
    from: "supplier-gland-bpi",
    id: "e-gland-fda-source",
    risk: "watch",
    riskScore: 44,
    to: "source-fda-carboplatin",
  },
  {
    from: "supplier-teva",
    id: "e-teva-fda-source",
    risk: "watch",
    riskScore: 30,
    to: "source-fda-carboplatin",
  },
  {
    from: "supplier-apotex",
    id: "e-apotex-fda-source",
    risk: "watch",
    riskScore: 42,
    to: "source-fda-carboplatin",
  },
  {
    from: "supplier-apotex",
    id: "e-apotex-discontinued",
    risk: "watch",
    riskScore: 42,
    to: "event-discontinued",
  },
  {
    from: "place-gujarat",
    id: "e-gujarat-ft-source",
    risk: "watch",
    riskScore: 46,
    to: "source-ft-intas",
  },
  {
    from: "component-platinum-raw",
    id: "e-raw-south-africa",
    risk: "elevated",
    riskScore: 50,
    to: "place-south-africa",
  },
  {
    from: "component-platinum-raw",
    id: "e-raw-marketwatch-source",
    risk: "elevated",
    riskScore: 50,
    to: "source-marketwatch-platinum",
  },
  {
    from: "place-south-africa",
    id: "e-south-africa-marketwatch-source",
    risk: "elevated",
    riskScore: 50,
    to: "source-marketwatch-platinum",
  },
  {
    from: "place-south-africa",
    id: "e-south-africa-deficit",
    risk: "watch",
    riskScore: 37,
    to: "event-platinum-deficit",
  },
  {
    from: "event-fda-shortage",
    id: "e-shortage-fda-source",
    risk: "critical",
    riskScore: 82,
    to: "source-fda-carboplatin",
  },
  {
    from: "event-fda-shortage",
    id: "e-shortage-ashp-source",
    risk: "critical",
    riskScore: 78,
    to: "source-ashp-carboplatin",
  },
  {
    from: "event-gmp",
    id: "e-gmp-fda-source",
    risk: "critical",
    riskScore: 82,
    to: "source-fda-carboplatin",
  },
  {
    from: "event-gmp",
    id: "e-gmp-ft-source",
    risk: "elevated",
    riskScore: 58,
    to: "source-ft-intas",
  },
  {
    from: "event-demand",
    id: "e-demand-fda-source",
    risk: "elevated",
    riskScore: 63,
    to: "source-fda-carboplatin",
  },
  {
    from: "event-shipping",
    id: "e-shipping-fda-source",
    risk: "elevated",
    riskScore: 59,
    to: "source-fda-carboplatin",
  },
  {
    from: "event-discontinued",
    id: "e-discontinued-fda-source",
    risk: "watch",
    riskScore: 43,
    to: "source-fda-carboplatin",
  },
  {
    from: "place-us-oncology",
    id: "e-us-oncology-axios",
    risk: "elevated",
    riskScore: 55,
    to: "source-axios-2023",
  },
  {
    from: "place-us-oncology",
    id: "e-us-oncology-nccn",
    risk: "elevated",
    riskScore: 53,
    to: "source-health-nccn",
  },
  {
    from: "event-platinum-deficit",
    id: "e-platinum-marketwatch",
    risk: "watch",
    riskScore: 35,
    to: "source-marketwatch-platinum",
  },
  {
    from: "event-api-shortage-2026",
    id: "e-api-shortage-times-india",
    risk: "elevated",
    riskScore: 52,
    scripted: true,
    to: scriptedSourceId,
  },
  {
    from: "event-fda-shortage",
    id: "e-shortage-times-india-evidence",
    risk: "elevated",
    riskScore: 54,
    scripted: true,
    to: scriptedSourceId,
  },
  {
    from: "component-platinum-api",
    id: "e-api-shortage-signal",
    risk: "elevated",
    riskScore: 57,
    scripted: true,
    to: "event-api-shortage-2026",
  },
];

export const medicineSupplyChainEdges: Record<string, string[]> = {
  [selectedMedicineId]: [
    "e-carboplatin-fda-source",
    "e-carboplatin-shortage",
    "e-shortage-accord",
    "e-carboplatin-api",
    "e-carboplatin-vial",
    "e-api-accord-intas",
    "e-api-times-india-source",
    "e-accord-gujarat",
    "e-accord-fda-source",
    "e-accord-gmp",
    "e-gmp-fda-source",
    "e-shortage-fda-source",
    "e-shortage-ashp-source",
    "e-vial-fda-source",
    "e-api-eugia",
    "e-eugia-fda-source",
    "e-eugia-demand",
    "e-demand-fda-source",
    "e-api-fresenius",
    "e-fresenius-fda-source",
    "e-fresenius-shipping",
    "e-shipping-fda-source",
    "e-api-pfizer",
    "e-pfizer-fda-source",
    "e-pfizer-demand",
    "e-api-gland-bpi",
    "e-gland-fda-source",
    "e-api-teva",
    "e-teva-fda-source",
    "e-api-apotex",
    "e-apotex-fda-source",
    "e-apotex-discontinued",
    "e-discontinued-fda-source",
    "e-api-raw-platinum",
    "e-raw-marketwatch-source",
    "e-raw-south-africa",
    "e-south-africa-marketwatch-source",
    "e-south-africa-deficit",
    "e-platinum-marketwatch",
    "e-gujarat-ft-source",
  ],
  "med-cisplatin": [
    "e-cisplatin-api",
    "e-cisplatin-fda-source",
    "e-api-accord-intas",
    "e-accord-gujarat",
    "e-accord-gmp",
    "e-gmp-ft-source",
    "e-api-raw-platinum",
    "e-raw-south-africa",
  ],
  "med-oxaliplatin": [
    "e-oxaliplatin-api",
    "e-oxaliplatin-fda-source",
    "e-api-raw-platinum",
    "e-raw-south-africa",
    "e-south-africa-deficit",
  ],
  "med-methotrexate": ["e-methotrexate-oncology-api", "e-methotrexate-ashp-source"],
  "med-ifosfamide": ["e-ifosfamide-oncology-api", "e-ifosfamide-ashp-source"],
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

const additionalSources = {
  ashpOncology: {
    meta: "ASHP, current shortage listings",
    title: "Current Drug Shortages",
    url: "https://www.ashp.org/drug-shortages/current-shortages",
  },
  fdaCisplatin: {
    meta: "FDA, related platinum chemotherapy",
    title: "Cisplatin Injection Shortage",
    url: "https://www.accessdata.fda.gov/scripts/drugshortages/dsp_ActiveIngredientDetails.cfm?AI=Cisplatin+Injection&st=c&tab=tabs-1",
  },
  fdaOxaliplatin: {
    meta: "FDA, related platinum chemotherapy",
    title: "Oxaliplatin Injection Shortage Listing",
    url: "https://www.accessdata.fda.gov/scripts/drugshortages/dsp_ActiveIngredientDetails.cfm?AI=Oxaliplatin+Injection&st=c&tab=tabs-1",
  },
  fdaSterileInjectables: {
    meta: "News analysis, generic sterile injectables",
    title: "Generic drugs in the US are too cheap to be sustainable",
    url: "https://www.theguardian.com/science/2024/jan/18/us-generic-drugs-prices-causing-shortage",
  },
  economicTimesApiCosts: {
    meta: "News, API and raw-material cost context",
    title: "Cancer drug prices raised 50% as NPPA acts on shortage concerns",
    url: "https://economictimes.indiatimes.com/industry/healthcare/biotech/pharmaceuticals/cancer-drug-prices-raised-50-as-nppa-acts-on-shortage-concerns/articleshow/131663737.cms",
  },
  wpicPlatinumQuarterly: {
    meta: "Industry market evidence",
    title: "Platinum Quarterly",
    url: "https://platinuminvestment.com/supply-and-demand/platinum-quarterly",
  },
};

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
  "component-sterile-vial": {
    confidence: "Context evidence",
    facts: [
      "Sterile injectable fill-finish capacity is a common constraint in drug shortages",
      "Evidence is contextual, not a direct carboplatin shortage cause",
      "This node explains why API availability alone is not enough",
    ],
    prompts: ["Explain risk path"],
    sources: [additionalSources.fdaSterileInjectables],
    whyItMatters:
      "The vial node represents the sterile manufacturing layer that turns active ingredient into hospital-ready injectable supply.",
  },
  "component-oncology-api": {
    confidence: "Clinical shortage context",
    facts: [
      "Oncology injectable shortages often share low-margin manufacturing fragility",
      "Used as a broader context node for methotrexate and ifosfamide",
      "This is not the main carboplatin action path",
    ],
    prompts: ["Explain risk path"],
    sources: [additionalSources.ashpOncology],
    whyItMatters:
      "The oncology API node shows that Sanitas can see category-level fragility beyond a single medicine.",
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
        meta: additionalSources.economicTimesApiCosts.meta,
        title: additionalSources.economicTimesApiCosts.title,
        url: additionalSources.economicTimesApiCosts.url,
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
        meta: additionalSources.wpicPlatinumQuarterly.meta,
        title: additionalSources.wpicPlatinumQuarterly.title,
        url: additionalSources.wpicPlatinumQuarterly.url,
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
  "supplier-eugia": {
    confidence: "Primary evidence, contextual branch",
    facts: [
      "FDA shortage rows list unavailable presentations tied to demand increase",
      "This branch is elevated context, not the selected action path",
    ],
    prompts: ["Explain risk path", "Review alternate supplier readiness"],
    sources: [primarySources[0]],
    whyItMatters:
      "Eugia helps show that backup suppliers can also be constrained when demand shifts during a shortage.",
  },
  "supplier-fresenius": {
    confidence: "Primary evidence, contextual branch",
    facts: [
      "FDA shortage rows include shipping-delay context",
      "Usable redundancy depends on delivery timing, not only supplier count",
    ],
    prompts: ["Explain risk path"],
    sources: [primarySources[0]],
    whyItMatters:
      "Fresenius Kabi is a visible redundancy branch where logistics timing can still limit hospital availability.",
  },
  "supplier-pfizer": {
    confidence: "Primary evidence, contextual branch",
    facts: [
      "FDA shortage rows include limited or unavailable presentations tied to demand increase",
      "This branch supports the need to verify approved alternatives",
    ],
    prompts: ["Check demand pressure", "Review alternate supplier readiness"],
    sources: [primarySources[0]],
    whyItMatters:
      "Pfizer / Hospira stays visible so the hospital user sees that alternate suppliers are not automatically usable supply.",
  },
  "supplier-gland-bpi": {
    confidence: "Primary evidence, watch branch",
    facts: [
      "FDA shortage rows include discontinued presentations",
      "Discontinuations reduce backup options",
    ],
    prompts: ["Explain risk path"],
    sources: [primarySources[0]],
    whyItMatters:
      "Gland / BPI Labs is a lower-intensity branch showing how product discontinuations narrow fallback capacity.",
  },
  "supplier-teva": {
    confidence: "Visible redundancy context",
    facts: [
      "Lower-risk supplier branch retained for graph completeness",
      "Evidence should be treated as listing context rather than a critical constraint",
    ],
    prompts: ["Review alternate supplier readiness"],
    sources: [primarySources[0]],
    whyItMatters:
      "Teva provides a calmer supplier reference so the graph does not imply every supplier is equally urgent.",
  },
  "supplier-apotex": {
    confidence: "Primary evidence, watch branch",
    facts: [
      "FDA shortage rows include discontinued presentations",
      "Discontinued presentations can reduce practical redundancy",
    ],
    prompts: ["Explain risk path"],
    sources: [primarySources[0]],
    whyItMatters:
      "Teyro / Apotex is a watch branch that supports alternate-supplier checks without becoming the demo's red path.",
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
  "source-fda-cisplatin": {
    confidence: "Primary Evidence Satellite",
    facts: [
      "Related platinum chemotherapy shortage context",
      "Supports shared upstream exposure for the overview graph",
    ],
    prompts: ["Explain risk path"],
    sources: [additionalSources.fdaCisplatin],
    whyItMatters:
      "This source supports the related cisplatin node without shifting the demo away from carboplatin.",
  },
  "source-fda-oxaliplatin": {
    confidence: "Primary Evidence Satellite",
    facts: [
      "Related platinum chemotherapy listing context",
      "Supports shared platinum chemotherapy monitoring",
    ],
    prompts: ["Explain risk path"],
    sources: [additionalSources.fdaOxaliplatin],
    whyItMatters: "This source supports the related oxaliplatin node as category context.",
  },
  "source-ashp-oncology": {
    confidence: "Clinical Evidence Satellite",
    facts: [
      "Clinical shortage list context for oncology medicines",
      "Used as supporting evidence for watch-level oncology branches",
    ],
    prompts: ["Explain risk path"],
    sources: [additionalSources.ashpOncology],
    whyItMatters:
      "This source keeps lower-priority oncology risks evidence-backed without creating another action path.",
  },
  "source-fda-sterile-injectables": {
    confidence: "Context Evidence Satellite",
    facts: [
      "News analysis of generic sterile injectable shortage economics",
      "Supports sterile-injectable manufacturing fragility as a general risk factor",
    ],
    prompts: ["Explain risk path"],
    sources: [additionalSources.fdaSterileInjectables],
    whyItMatters:
      "This source backs the sterile injectable layer as context rather than direct carboplatin proof.",
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
      "Supports platinum-market pressure and supply deficit context",
      "Risk amplifier only, not direct shortage causality",
    ],
    prompts: ["Find newer evidence"],
    sources: [additionalSources.wpicPlatinumQuarterly],
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
