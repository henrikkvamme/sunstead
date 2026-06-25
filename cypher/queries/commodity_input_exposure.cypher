MATCH path = (c:Commodity {key: $commodity_key})-[:LINKED_TO_COMMODITY|USES_INPUT|SUPPLIES_INPUT|CONTAINS_EXCIPIENT|CONTAINS_ACTIVE_INGREDIENT|MANUFACTURED_BY*1..5]-(n)
WHERE n:ChemicalInput OR n:RawMaterial OR n:Excipient OR n:ActiveIngredient OR n:Drug OR n:Supplier OR n:Manufacturer
RETURN path
LIMIT 100;
