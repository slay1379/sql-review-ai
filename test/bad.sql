-- 수정 전 (반려)
select * from users where id = 1

-- 수정 후 (통과 예상)
SELECT id, email, name FROM users WHERE id = 1;
