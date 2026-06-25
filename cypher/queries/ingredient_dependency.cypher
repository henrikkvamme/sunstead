MATCH path = (i:ActiveIngredient {key: $ingredient_key})-[:CONTAINS_ACTIVE_INGREDIENT|USES_INPUT|LINKED_TO_COMMODITY|SUPPLIES_INPUT|SUPPLIES|MANUFACTURED_BY*1..5]-(n)
WHERE n:Drug OR n:NDC OR n:Manufacturer OR n:Supplier OR n:Facility OR n:Commodity
RETURN path
LIMIT 100;
