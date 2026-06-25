import { createFileRoute } from "@tanstack/react-router";
import { z } from "zod";

import { createSupplyRiskAgentUIResponse } from "#/ai";

const agentRequestSchema = z.object({
  messages: z.array(z.unknown()),
  modelId: z.string().min(1).optional(),
});

export const Route = createFileRoute("/api/agent")({
  server: {
    handlers: {
      POST: async ({ request }) => {
        const body = await request.json().catch(() => null);
        const parsed = agentRequestSchema.safeParse(body);

        if (!parsed.success) {
          return Response.json(
            {
              error: "Invalid agent request body.",
              issues: parsed.error.issues,
            },
            { status: 400 },
          );
        }

        return createSupplyRiskAgentUIResponse({
          abortSignal: request.signal,
          messages: parsed.data.messages,
          modelId: parsed.data.modelId,
        });
      },
    },
  },
});
