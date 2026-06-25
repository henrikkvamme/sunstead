MATCH path = (r:RiskCase {key: $risk_case_key})-[*1..3]-(n)
RETURN path
LIMIT 100;

