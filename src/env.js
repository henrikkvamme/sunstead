export function getProcessEnv() {
  return typeof process === "undefined" ? {} : process.env;
}

export function readServerEnv(env = getProcessEnv()) {
  return {
    ANTHROPIC_API_BASE_URL: readOptionalEnv(env, "ANTHROPIC_API_BASE_URL"),
    ANTHROPIC_API_KEY: readOptionalEnv(env, "ANTHROPIC_API_KEY"),
    CLAUDE_MANAGED_AGENT_ID: readOptionalEnv(env, "CLAUDE_MANAGED_AGENT_ID"),
    CLAUDE_MANAGED_ENVIRONMENT_ID: readOptionalEnv(env, "CLAUDE_MANAGED_ENVIRONMENT_ID"),
    SUNSTEAD_AI_MODEL: readOptionalEnv(env, "SUNSTEAD_AI_MODEL"),
  };
}

export const serverEnv = readServerEnv();

function readOptionalEnv(env, key) {
  const value = env[key];

  return value && value.trim().length > 0 ? value.trim() : undefined;
}
