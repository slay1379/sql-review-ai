-- 정상 SELECT 쿼리 (성공해야 함)

SELECT
    customer_id,
    name
FROM
    customers
WHERE
    status = 'ACTIVE';
