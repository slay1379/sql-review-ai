-- [TEST] PR Comment Auto-Generation Test Query
-- 의도적인 오류 포함: 
-- 1. 소문자 예약어 사용 (select, from, where)
-- 2. SELECT * (Wildcard) 사용으로 인한 성능 경고 유발
-- 3. WHERE 절 줄바꿈 규칙 위반

select * from accounts where status = 'ACTIVE';

-- (옵션) 아래 주석을 풀면 '고위험 차단' 테스트가 됩니다.
-- DELETE FROM users WHERE id = 1;
