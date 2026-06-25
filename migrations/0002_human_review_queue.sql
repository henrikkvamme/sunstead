CREATE TABLE IF NOT EXISTS human_review_queue (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  target_table text NOT NULL,
  target_id uuid NOT NULL,
  review_type text NOT NULL,
  reason text NOT NULL,
  status text NOT NULL,
  priority text NOT NULL,
  evidence_span_ids uuid[] NOT NULL DEFAULT '{}',
  schema_version int NOT NULL DEFAULT 1,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (target_table, target_id)
);

CREATE INDEX IF NOT EXISTS human_review_queue_status_priority_idx
  ON human_review_queue (status, priority, created_at DESC);

CREATE INDEX IF NOT EXISTS human_review_queue_target_idx
  ON human_review_queue (target_table, target_id);

CREATE INDEX IF NOT EXISTS human_review_queue_evidence_span_ids_gin_idx
  ON human_review_queue USING gin (evidence_span_ids);
