import json
from datetime import UTC, datetime
from pathlib import Path

from supply_intel.db.repositories.evidence import FileEvidenceStore
from supply_intel.entity_resolution.service import EntityResolutionService
from supply_intel.models.documents import DocumentChunk, EvidenceSpan
from supply_intel.models.extraction import ExtractionRun
from supply_intel.models.medical import MedicalEntity
from supply_intel.models.source import RawDocument
from supply_intel.pipeline import ingest_openfda_ndc_fixture, resolve_and_store_entity
from supply_intel.settings import Settings
from supply_intel.sources.registry import load_source_config

EXPECTED_NDC_ENTITIES = 4


def test_ndc_ingestion_persists_entity_resolution_artifacts(tmp_path: Path) -> None:
    config = load_source_config(Path("sources/openfda_drug_ndc.yaml"))
    settings = Settings(data_dir=tmp_path)

    stats = ingest_openfda_ndc_fixture(
        config=config,
        fixture_path=Path("tests/fixtures/sources/openfda_drug_ndc/success.json"),
        settings=settings,
        max_documents=1,
    )

    assert stats["canonical_entities"] == EXPECTED_NDC_ENTITIES
    assert stats["entity_mentions"] == EXPECTED_NDC_ENTITIES
    canonical_entities = _read_jsonl(tmp_path / "canonical_entities.jsonl")
    aliases = _read_jsonl(tmp_path / "entity_aliases.jsonl")
    mentions = _read_jsonl(tmp_path / "entity_mentions.jsonl")
    assert len(canonical_entities) == EXPECTED_NDC_ENTITIES
    assert {row["entity_type"] for row in canonical_entities} >= {
        "Drug",
        "NDC",
        "ActiveIngredient",
        "Manufacturer",
    }
    assert any(row["alias_type"] == "external_id" for row in aliases)
    assert all(row["evidence_span_id"] for row in mentions)
    assert all(row["extraction_run_id"] for row in mentions)


def test_low_confidence_high_impact_entity_creates_review_task(tmp_path: Path) -> None:
    store = FileEvidenceStore(tmp_path)
    resolver = EntityResolutionService()
    document = RawDocument(
        source_id="manual_seed",
        source_run_id="00000000-0000-0000-0000-000000000001",
        source_url="file://seed.json",
        content_hash="hash",
        payload_storage="inline",
        payload_text="{}",
        dedupe_key="seed",
    )
    chunk = DocumentChunk(
        raw_document_id=document.id,
        chunk_index=0,
        chunk_type="json_record",
        text="Acme Manufacturing",
        content_hash="chunk-hash",
    )
    evidence_span = EvidenceSpan(
        raw_document_id=document.id,
        document_chunk_id=chunk.id,
        source_id=document.source_id,
        source_url=document.source_url,
        quote=chunk.text,
        confidence=0.75,
        evidence_type="source_record",
        hash="evidence-hash",
    )
    extraction_run = ExtractionRun(
        raw_document_id=document.id,
        document_chunk_id=chunk.id,
        agent_name="test-agent",
        agent_version="1",
        model_name="deterministic",
        prompt_hash="prompt",
        input_hash="input",
        output_schema="MedicalExtractionOutput",
        status="succeeded",
        finished_at=datetime.now(UTC),
        idempotency_key="extract:test",
    )
    entity = MedicalEntity(
        entity_type="Manufacturer",
        name="Acme Manufacturing",
        canonical_key="Manufacturer:name:acme_manufacturing",
        confidence=0.75,
    )
    stats: dict[str, int] = {}

    resolve_and_store_entity(
        store=store,
        resolver=resolver,
        entity=entity,
        document=document,
        chunk=chunk,
        extraction_run=extraction_run,
        evidence_span=evidence_span,
        stats=stats,
    )

    reviews = _read_jsonl(tmp_path / "human_review_queue.jsonl")
    feedback = _read_jsonl(tmp_path / "human_feedback.jsonl")
    canonical_entities = _read_jsonl(tmp_path / "canonical_entities.jsonl")
    assert stats["human_review_tasks"] == 1
    assert canonical_entities[0]["needs_review"] is True
    assert reviews[0]["review_type"] == "low_confidence"
    assert reviews[0]["target_id"] == canonical_entities[0]["id"]
    assert reviews[0]["evidence_span_ids"] == [str(evidence_span.id)]
    assert feedback[0]["target_table"] == "canonical_entities"
    assert feedback[0]["target_id"] == canonical_entities[0]["id"]
    assert feedback[0]["feedback_type"] == "review_requested"
    assert feedback[0]["decision"] == "pending"
    assert feedback[0]["metadata"]["human_review_task_id"] == reviews[0]["id"]


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
