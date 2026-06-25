MATCH path = (d:Drug {key: $drug_key})-[*1..4]-(n)
RETURN path
LIMIT 100;

