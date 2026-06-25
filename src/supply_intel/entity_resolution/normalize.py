import re
import unicodedata


def normalize_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    normalized = re.sub(r"\b(incorporated|inc|corp|corporation|ltd|llc|gmbh|co)\b", "", normalized)
    return " ".join(normalized.split())


def stable_entity_key(entity_type: str, name: str) -> str:
    return f"{entity_type}:name:{normalize_name(name).replace(' ', '_')}"
