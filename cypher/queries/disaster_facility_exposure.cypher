MATCH path = (d:DisasterEvent {key: $disaster_key})-[:AFFECTS|LOCATED_IN|NEAR_PORT|CONNECTS|OPERATES|PRODUCES|MANUFACTURED_AT*1..5]-(n)
WHERE n:Region OR n:Country OR n:City OR n:Port OR n:Facility OR n:Supplier OR n:Manufacturer OR n:Drug OR n:MedicalDevice
RETURN path
LIMIT 100;
