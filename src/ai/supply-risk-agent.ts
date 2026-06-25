import {
  ToolLoopAgent,
  createAgentUIStreamResponse,
  gateway,
  stepCountIs,
  type GatewayModelId,
  type InferAgentUIMessage,
} from "ai";

import { readServerEnv } from "#/env";

import { buildSupplyRiskAgentInstructions } from "./prompts";
import {
  createSupplyRiskAgentTools,
  supplyRiskAgentTools,
  type CreateSupplyRiskAgentToolsOptions,
} from "./tools";

export const defaultSupplyRiskAgentModel = "anthropic/claude-sonnet-4.5";
export const supplyRiskAgentId = "supply-risk-investigator";

export type CreateSupplyRiskAgentOptions = CreateSupplyRiskAgentToolsOptions & {
  maxSteps?: number;
  modelId?: string;
  temperature?: number;
  today?: Date;
};

export type SupplyRiskAgentUIResponseOptions = CreateSupplyRiskAgentOptions & {
  abortSignal?: AbortSignal;
  messages: unknown[];
};

export function getSupplyRiskAgentModelId(
  modelId: string | undefined = readServerEnv().SUNSTEAD_AI_MODEL,
) {
  return (modelId || defaultSupplyRiskAgentModel) as GatewayModelId;
}

export function createSupplyRiskAgent(options: CreateSupplyRiskAgentOptions = {}) {
  return new ToolLoopAgent({
    id: supplyRiskAgentId,
    instructions: buildSupplyRiskAgentInstructions(options.today),
    model: gateway(getSupplyRiskAgentModelId(options.modelId)),
    stopWhen: stepCountIs(options.maxSteps ?? 8),
    temperature: options.temperature ?? 0.2,
    tools:
      options.managedInvestigation === undefined
        ? supplyRiskAgentTools
        : createSupplyRiskAgentTools({ managedInvestigation: options.managedInvestigation }),
  });
}

export type SupplyRiskAgent = ReturnType<typeof createSupplyRiskAgent>;
export type SupplyRiskAgentUIMessage = InferAgentUIMessage<SupplyRiskAgent>;

export async function generateSupplyRiskAgentText(
  prompt: string,
  options: CreateSupplyRiskAgentOptions = {},
) {
  const agent = createSupplyRiskAgent(options);

  return agent.generate({ prompt });
}

export function createSupplyRiskAgentUIResponse({
  abortSignal,
  messages,
  ...agentOptions
}: SupplyRiskAgentUIResponseOptions) {
  return createAgentUIStreamResponse({
    abortSignal,
    agent: createSupplyRiskAgent(agentOptions),
    uiMessages: messages,
  });
}
