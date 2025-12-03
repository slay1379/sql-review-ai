-- tests/warn_select_star.sql
-- SELECT * 사용으로 성능/보안 경고는 나오지만, BLOCK 되면 안 되는 케이스
-- 돼라 제발

SELECT
    *
FROM
    accounts
WHERE
    status = 'ACTIVE';
