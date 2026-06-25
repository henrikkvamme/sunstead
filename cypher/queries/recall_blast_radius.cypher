MATCH path = (r:Recall {key: $recall_key})-[:AFFECTS|INVOLVES|ABOUT|MENTIONS|SUPPORTED_BY|HAS_EVIDENCE|MANUFACTURED_BY|HAS_NDC*1..4]-(n)
WHERE n:Drug OR n:NDC OR n:MedicalDevice OR n:Manufacturer OR n:Facility OR n:EvidenceDocument
RETURN path
LIMIT 100;
