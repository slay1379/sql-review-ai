-- tests/good.sql

SELECT
    customer_id,
    name,
    status
FROM
    customers
WHERE
    status = 'ACTIVE';
