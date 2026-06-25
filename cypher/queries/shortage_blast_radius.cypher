MATCH path = (s:Shortage {key: $shortage_key})-[:AFFECTS|INVOLVES|ABOUT|MENTIONS|SUPPORTED_BY|HAS_EVIDENCE|CONTAINS_ACTIVE_INGREDIENT|MANUFACTURED_BY*1..4]-(n)
WHERE n:Drug OR n:NDC OR n:ActiveIngredient OR n:Manufacturer OR n:Facility OR n:EvidenceDocument
RETURN path
LIMIT 100;
