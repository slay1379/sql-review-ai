# examples/app_example.py
# 코드 안에 박혀 있는 SQL 테스트용

def get_active_customers_query():
    # 안전한 쿼리
    sql = """
    SELECT
        customer_id,
        name
    FROM
        customers
    WHERE
        status = 'ACTIVE';
    """
    return sql


def dangerous_delete_query():
    # 고위험 쿼리: 만약 워크플로우가 .py에서 SQL을 추출한다면 BLOCK 되어야 함
    sql = "DELETE FROM customers WHERE rrn = '990101-1234567';"
    return sql
