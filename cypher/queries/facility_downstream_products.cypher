MATCH path = (f:Facility {key: $facility_key})-[:PRODUCES|MANUFACTURED_AT|MANUFACTURED_BY|LABELS|HAS_NDC|CONTAINS_ACTIVE_INGREDIENT*1..5]-(n)
WHERE n:Drug OR n:NDC OR n:MedicalDevice OR n:ActiveIngredient OR n:Manufacturer
RETURN path
LIMIT 100;
