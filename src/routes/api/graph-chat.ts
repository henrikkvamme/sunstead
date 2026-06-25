import { appendFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";

import { createFileRoute } from "@tanstack/react-router";
import { z } from "zod";

import { answerSupplyGraphQuestion, type GraphChatAuditRecord } from "#/ai";

const graphChatRequestSchema = z.object({
  limit: z.number().int().min(1).max(12).optional(),
  nodeId: z.string().min(1).optional(),
  question: z.string().trim().min(1).max(1200),
});

function graphChatAuditPath() {
  return (
    process.env.GRAPH_CHAT_AUDIT_PATH ||
    join(process.env.DATA_DIR || ".data", "dashboard_graph_chat_audit.jsonl")
  );
}

function writeGraphChatAudit(record: GraphChatAuditRecord) {
  if (process.env.GRAPH_CHAT_AUDIT_DISABLED === "true") {
    return;
  }

  const path = graphChatAuditPath();

  mkdirSync(dirname(path), { recursive: true });
  appendFileSync(path, `${JSON.stringify(record)}\n`, "utf8");
}

export const Route = createFileRoute("/api/graph-chat")({
  server: {
    handlers: {
      POST: async ({ request }) => {
        const body = await request.json().catch(() => null);
        const parsed = graphChatRequestSchema.safeParse(body);

        if (!parsed.success) {
          return Response.json(
            {
              error: "Invalid graph chat request body.",
              issues: parsed.error.issues,
            },
            { status: 400 },
          );
        }

        const answer = answerSupplyGraphQuestion(parsed.data);

        writeGraphChatAudit(answer.audit);

        return Response.json(answer);
      },
    },
  },
});
