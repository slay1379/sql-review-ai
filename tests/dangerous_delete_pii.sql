-- tests/dangerous_delete_pii.sql
-- DELETE + 주민번호(PII) → 무조건 BLOCK 되어야 하는 케이스

DELETE
FROM customers
WHERE rrn = '900101-1234567';
