import { buildNodeInvestigationPrompt, type NodeInvestigationPromptInput } from "./prompts";

export const claudeManagedAgentsBetaHeader = "managed-agents-2026-04-01";
export const defaultAnthropicApiBaseUrl = "https://api.anthropic.com";
export const anthropicApiVersion = "2023-06-01";

export type ClaudeManagedAgentConfig = {
  agentId: string;
  apiKey: string;
  baseUrl?: string;
  environmentId: string;
};

export type ClaudeManagedAgentConfigState =
  | {
      config: ClaudeManagedAgentConfig;
      configured: true;
      missing: [];
    }
  | {
      configured: false;
      missing: Array<keyof ClaudeManagedAgentConfig>;
    };

export type ClaudeManagedAgentSession = {
  id: string;
  status?: string;
  type?: string;
  usage?: unknown;
};

export type ClaudeManagedAgentEventContent = {
  text: string;
  type: "text";
};

export type ClaudeManagedAgentUserEvent = {
  content: ClaudeManagedAgentEventContent[];
  type: "user.message";
};

export type ClaudeManagedSourceInvestigationInput = NodeInvestigationPromptInput & {
  sessionId?: string;
};

export type ClaudeManagedSourceInvestigationResult =
  | {
      configured: false;
      missing: Array<keyof ClaudeManagedAgentConfig>;
      provider: "claude-managed-agents";
      status: "not_configured";
    }
  | {
      configured: true;
      provider: "claude-managed-agents";
      sessionId: string;
      status: "started" | "resumed";
      streamUrl: string;
    };

export type ClaudeManagedAgentFetch = typeof fetch;

export function resolveClaudeManagedAgentConfig(
  env: NodeJS.ProcessEnv = process.env,
): ClaudeManagedAgentConfigState {
  const config = {
    agentId: env.CLAUDE_MANAGED_AGENT_ID ?? "",
    apiKey: env.ANTHROPIC_API_KEY ?? "",
    baseUrl: env.ANTHROPIC_API_BASE_URL,
    environmentId: env.CLAUDE_MANAGED_ENVIRONMENT_ID ?? "",
  };
  const missing: Array<keyof ClaudeManagedAgentConfig> = [];

  if (!config.apiKey) {
    missing.push("apiKey");
  }

  if (!config.agentId) {
    missing.push("agentId");
  }

  if (!config.environmentId) {
    missing.push("environmentId");
  }

  if (missing.length > 0) {
    return { configured: false, missing };
  }

  return { configured: true, config, missing: [] };
}

export function buildClaudeManagedAgentUserEvent(text: string): ClaudeManagedAgentUserEvent {
  return {
    type: "user.message",
    content: [{ type: "text", text }],
  };
}

export class ClaudeManagedAgentClient {
  readonly config: ClaudeManagedAgentConfig;
  readonly fetch: ClaudeManagedAgentFetch;

  constructor(
    config: ClaudeManagedAgentConfig,
    fetchImplementation: ClaudeManagedAgentFetch = fetch,
  ) {
    this.config = config;
    this.fetch = fetchImplementation;
  }

  get baseUrl() {
    return (this.config.baseUrl ?? defaultAnthropicApiBaseUrl).replace(/\/$/, "");
  }

  get streamUrlBase() {
    return `${this.baseUrl}/v1/sessions`;
  }

  async createSession(options?: { signal?: AbortSignal }) {
    return this.request<ClaudeManagedAgentSession>("/v1/sessions", {
      body: {
        agent: this.config.agentId,
        environment_id: this.config.environmentId,
      },
      method: "POST",
      signal: options?.signal,
    });
  }

  async sendUserMessage(sessionId: string, text: string, options?: { signal?: AbortSignal }) {
    return this.request<unknown>(`/v1/sessions/${sessionId}/events`, {
      body: {
        events: [buildClaudeManagedAgentUserEvent(text)],
      },
      method: "POST",
      signal: options?.signal,
    });
  }

  streamSessionEvents(sessionId: string, options?: { signal?: AbortSignal }) {
    return this.fetch(`${this.streamUrlBase}/${sessionId}/stream`, {
      headers: this.headers({ accept: "text/event-stream" }),
      method: "GET",
      signal: options?.signal,
    });
  }

  private async request<T>(
    path: string,
    {
      body,
      method,
      signal,
    }: {
      body?: unknown;
      method: "GET" | "POST";
      signal?: AbortSignal;
    },
  ) {
    const response = await this.fetch(`${this.baseUrl}${path}`, {
      body: body === undefined ? undefined : JSON.stringify(body),
      headers: this.headers(),
      method,
      signal,
    });

    if (!response.ok) {
      const errorBody = await response.text().catch(() => "");

      throw new Error(
        `Claude Managed Agents request failed: ${response.status} ${response.statusText}${errorBody ? ` ${errorBody}` : ""}`,
      );
    }

    return (await response.json()) as T;
  }

  private headers(options: { accept?: string } = {}) {
    return {
      "anthropic-beta": claudeManagedAgentsBetaHeader,
      "anthropic-version": anthropicApiVersion,
      "content-type": "application/json",
      "x-api-key": this.config.apiKey,
      ...(options.accept ? { accept: options.accept } : {}),
    };
  }
}

export type StartClaudeManagedSourceInvestigationOptions = {
  client?: ClaudeManagedAgentClient;
  config?: ClaudeManagedAgentConfig;
  signal?: AbortSignal;
};

export async function startClaudeManagedSourceInvestigation(
  input: ClaudeManagedSourceInvestigationInput,
  options: StartClaudeManagedSourceInvestigationOptions = {},
): Promise<ClaudeManagedSourceInvestigationResult> {
  const resolved = options.config
    ? { configured: true as const, config: options.config, missing: [] as [] }
    : resolveClaudeManagedAgentConfig();

  let client = options.client;

  if (!client) {
    if (!resolved.configured) {
      return {
        configured: false,
        missing: resolved.missing,
        provider: "claude-managed-agents",
        status: "not_configured",
      };
    }

    client = new ClaudeManagedAgentClient(resolved.config);
  }

  const prompt = buildNodeInvestigationPrompt(input);
  const session =
    input.sessionId === undefined
      ? await client.createSession({ signal: options.signal })
      : { id: input.sessionId };

  await client.sendUserMessage(session.id, prompt, { signal: options.signal });

  return {
    configured: true,
    provider: "claude-managed-agents",
    sessionId: session.id,
    status: input.sessionId === undefined ? "started" : "resumed",
    streamUrl: `${client.streamUrlBase}/${session.id}/stream`,
  };
}
