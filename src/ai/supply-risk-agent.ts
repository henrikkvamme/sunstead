import { createAnthropic } from "@ai-sdk/anthropic";
import {
  ToolLoopAgent,
  createAgentUIStreamResponse,
  stepCountIs,
  type InferAgentUIMessage,
} from "ai";

import { readServerEnv, type SunsteadServerEnv } from "#/env";

import { isSupplyRiskAgentScenario, type SupplyRiskAgentScenario } from "./carboplatin-demo";
import { buildSupplyRiskAgentInstructions } from "./prompts";
import {
  createSupplyRiskAgentTools,
  supplyRiskAgentTools,
  type CreateSupplyRiskAgentToolsOptions,
} from "./tools";

export const defaultSupplyRiskAgentModel = "claude-sonnet-4-6";
export const supplyRiskAgentId = "supply-risk-investigator";

export type CreateSupplyRiskAgentOptions = CreateSupplyRiskAgentToolsOptions & {
  maxSteps?: number;
  modelId?: string;
  scenario?: SupplyRiskAgentScenario;
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
  return normalizeAnthropicModelId(modelId || defaultSupplyRiskAgentModel);
}

export function createSupplyRiskAnthropicModel(
  modelId = getSupplyRiskAgentModelId(),
  env: SunsteadServerEnv = readServerEnv(),
) {
  const anthropic = createAnthropic({
    apiKey: env.ANTHROPIC_API_KEY,
    baseURL: env.ANTHROPIC_BASE_URL,
  });

  return anthropic(modelId);
}

export function createSupplyRiskAgent(options: CreateSupplyRiskAgentOptions = {}) {
  const isDemoScenario = isSupplyRiskAgentScenario(options.scenario);

  return new ToolLoopAgent({
    id: supplyRiskAgentId,
    instructions: buildSupplyRiskAgentInstructions(options.today, { scenario: options.scenario }),
    model: createSupplyRiskAnthropicModel(getSupplyRiskAgentModelId(options.modelId)),
    stopWhen: stepCountIs(options.maxSteps ?? (isDemoScenario ? 5 : 8)),
    temperature: options.temperature ?? (isDemoScenario ? 0.1 : 0.2),
    tools:
      options.managedInvestigation === undefined && options.scenario === undefined
        ? supplyRiskAgentTools
        : createSupplyRiskAgentTools({
            managedInvestigation: options.managedInvestigation,
            scenario: options.scenario,
          }),
  });
}

function normalizeAnthropicModelId(modelId: string) {
  return modelId.replace(/^anthropic\//, "").replace("claude-sonnet-4.6", "claude-sonnet-4-6");
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
