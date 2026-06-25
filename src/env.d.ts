export type SunsteadServerEnv = {
  ANTHROPIC_API_BASE_URL?: string;
  ANTHROPIC_API_KEY?: string;
  CLAUDE_MANAGED_AGENT_ID?: string;
  CLAUDE_MANAGED_ENVIRONMENT_ID?: string;
  SUNSTEAD_AI_MODEL?: string;
};

export function getProcessEnv(): NodeJS.ProcessEnv;

export function readServerEnv(env?: NodeJS.ProcessEnv): SunsteadServerEnv;

export const serverEnv: SunsteadServerEnv;
