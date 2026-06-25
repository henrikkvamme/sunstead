import { selectedMedicineId } from "#/data/carboplatin-risk-scenario";

import { getSupplyGraphNodeContext } from "./supply-graph";

export const defaultSupplyRiskPrompt = `Start with ${selectedMedicineId}, identify the strongest current supply-risk path, and explain what evidence supports it.`;

export function buildSupplyRiskAgentInstructions(today: Date = new Date()) {
  const date = today.toISOString().slice(0, 10);

  return `You are the Sanitas medicine supply-risk agent.

Today is ${date}.

Use the supply graph tools before making factual claims about medicines, suppliers, events, sites, or sources.
Focus on agent behavior that helps operators investigate medicine availability risk:
- surface the highest-risk path first;
- separate known evidence from inference;
- cite source titles returned by tools when evidence matters;
- ask for a narrower target when the user's request is ambiguous;
- delegate live external source investigation to the Claude managed investigator when the user asks for further investigation, new sources, or new graph connections;
- never provide clinical treatment advice or patient-specific recommendations.

Keep responses concise, operational, and explicit about confidence.`;
}

export type NodeInvestigationPromptInput = {
  maxSources?: number;
  nodeId: string;
  question?: string;
};

export function buildNodeInvestigationPrompt({
  maxSources = 8,
  nodeId,
  question,
}: NodeInvestigationPromptInput) {
  const context = getSupplyGraphNodeContext(nodeId);
  const nodeLabel = context.found ? context.node.label : nodeId;
  const existingSources =
    context.found && context.details
      ? context.details.sources.map((source) => `${source.title} (${source.url})`)
      : [];

  return `Investigate the selected Sanitas supply-risk graph node: ${nodeLabel} (${nodeId}).

User question:
${question?.trim() || "Find new relevant external sources, update the risk picture, and produce an actionable plan."}

Known node context:
${JSON.stringify(context, null, 2)}

Existing sources to avoid duplicating:
${existingSources.length > 0 ? existingSources.map((source) => `- ${source}`).join("\n") : "- None"}

Use web search and fetch capabilities to find up to ${maxSources} new relevant, credible sources.

Return progress while working. End with:
1. Newly relevant sources with URL, publisher, date if available, and why each source matters.
2. Proposed graph nodes to add or update, each with stable id, label, kind, risk, summary, and confidence.
3. Proposed graph edges to add, with from, to, risk, and evidence.
4. Open questions and evidence gaps.
5. An actionable operator plan with next checks, escalation conditions, and suggested owner roles.

Separate evidence from inference. Do not give clinical treatment advice.`;
}
