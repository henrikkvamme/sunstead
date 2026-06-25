MATCH path = (p:Port {key: $port_key})-[:NEAR_PORT|CONNECTS|LOCATED_IN|SUPPLIES|SUPPLIES_INPUT|MANUFACTURED_AT|PRODUCES*1..5]-(n)
WHERE n:Facility OR n:Supplier OR n:Manufacturer OR n:TransportRoute OR n:Drug OR n:MedicalDevice
RETURN path
LIMIT 100;
