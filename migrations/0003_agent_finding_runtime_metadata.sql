ALTER TABLE agent_findings
  ADD COLUMN IF NOT EXISTS model_name text NOT NULL DEFAULT 'deterministic-local',
  ADD COLUMN IF NOT EXISTS prompt_hash text NOT NULL DEFAULT 'deterministic_agent_finding_v1',
  ADD COLUMN IF NOT EXISTS input_hash text NOT NULL DEFAULT 'not_recorded',
  ADD COLUMN IF NOT EXISTS output_schema text NOT NULL DEFAULT 'AgentFinding',
  ADD COLUMN IF NOT EXISTS output_schema_version int NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS usage jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS error text;

CREATE INDEX IF NOT EXISTS agent_findings_runtime_idx
  ON agent_findings (agent_name, model_name, output_schema, output_schema_version);

CREATE INDEX IF NOT EXISTS agent_findings_prompt_input_idx
  ON agent_findings (prompt_hash, input_hash);
