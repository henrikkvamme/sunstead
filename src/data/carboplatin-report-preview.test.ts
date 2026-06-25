import { describe, expect, it } from "vite-plus/test";

import {
  carboplatinReportPreview,
  graphNodes,
  scriptedSourceId,
  supplierRiskPath,
} from "./carboplatin-risk-scenario";

describe("carboplatin report preview", () => {
  it("uses the supplier Risk Path instead of the evidence traversal", () => {
    expect(carboplatinReportPreview.actionPathNodeIds).toEqual(supplierRiskPath);
  });

  it("points report evidence to existing Evidence Source nodes", () => {
    const graphNodeIds = new Set(graphNodes.map((node) => node.id));

    expect(carboplatinReportPreview.evidenceSourceNodeIds).toEqual([
      "source-fda-carboplatin",
      "source-ashp-carboplatin",
      scriptedSourceId,
    ]);
    expect(
      carboplatinReportPreview.evidenceSourceNodeIds.every((sourceId) =>
        graphNodeIds.has(sourceId),
      ),
    ).toBe(true);
    expect(
      carboplatinReportPreview.evidenceSourceNodeIds.every(
        (sourceId) => graphNodes.find((node) => node.id === sourceId)?.kind === "source",
      ),
    ).toBe(true);
  });

  it("keeps primary shortage sources ahead of supporting API evidence", () => {
    expect(carboplatinReportPreview.evidenceSourceNodeIds.indexOf("source-fda-carboplatin")).toBe(
      0,
    );
    expect(carboplatinReportPreview.evidenceSourceNodeIds.indexOf("source-ashp-carboplatin")).toBe(
      1,
    );
    expect(carboplatinReportPreview.evidenceSourceNodeIds.indexOf(scriptedSourceId)).toBe(2);
  });

  it("links to the light-mode PDF report asset", () => {
    expect(carboplatinReportPreview.pdfUrl).toBe("/reports/carboplatin-supply-risk-brief.pdf");
  });

  it("keeps caveats away from patient modeling and direct API causality", () => {
    const caveats = carboplatinReportPreview.caveats.join(" ");

    expect(caveats).toContain("not represented as patient-level data");
    expect(caveats).toContain("not the direct proven cause");
  });
});
