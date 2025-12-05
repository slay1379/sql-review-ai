SELECT
    customer_id,
    name,
    email
FROM
    customers
WHERE
    customer_id = '1'; -- customer_id는 VARCHAR 타입이므로 따옴표를 사용합니다.
