import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.util.List;
import java.math.BigDecimal;
import javax.persistence.EntityManager;
import javax.persistence.PersistenceContext;
import javax.persistence.TypedQuery;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class FinancialRepository {

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @PersistenceContext
    private EntityManager entityManager;

    /**
     * [CASE 1] JDBC PreparedStatement (고객 조회)
     * 보안: '?' 바인딩을 사용하여 customer_id 파라미터 조작 방지
     * 스키마: customers 테이블 (customer_id, name, encrypted_rrn, risk_score)
     */
    public void getCustomerCreditInfo(Connection conn, String customerId) throws SQLException {
        // 고객 ID로 이름, 암호화된 주민번호, 신용점수 조회
        String query = "SELECT name, encrypted_rrn, risk_score FROM customers WHERE customer_id = ?";
        
        try (PreparedStatement pstmt = conn.prepareStatement(query)) {
            pstmt.setString(1, customerId); // 바인딩 (Safe)
            
            try (ResultSet rs = pstmt.executeQuery()) {
                if (rs.next()) {
                    System.out.println("Customer: " + rs.getString("name"));
                    System.out.println("Score: " + rs.getInt("risk_score"));
                }
            }
        }
    }

    /**
     * [CASE 2] Spring JdbcTemplate (계좌 잔액 합계 조회)
     * 보안: 아규먼트 배열(Object[])을 통한 내부적 PreparedStatement 처리
     * 스키마: accounts 테이블 (balance, customer_id, status)
     */
    public BigDecimal getTotalBalanceByCustomer(String customerId) {
        // 특정 고객의 활성(ACTIVE) 계좌 총 잔액 계산
        String sql = "SELECT SUM(balance) FROM accounts WHERE customer_id = ? AND status = 'ACTIVE'";
        
        // 직접 문자열 결합 없이 파라미터 전달 (Safe)
        return jdbcTemplate.queryForObject(sql, new Object[]{customerId}, BigDecimal.class);
    }

    /**
     * [CASE 3] JPA JPQL (고액 거래 내역 조회)
     * 보안: Named Parameter (:minAmount, :type) 사용
     * 스키마: transactions 테이블 (amount, tx_type, tx_date)
     */
    public List<Object[]> findHighValueTransactions(BigDecimal minAmount, String txType) {
        // 특정 금액 이상의 거래 내역 조회 (예: 1000만원 이상 이체)
        String jpql = "SELECT t.txId, t.amount, t.merchantName " +
                      "FROM Transaction t " +
                      "WHERE t.amount >= :minAmount AND t.txType = :type " +
                      "ORDER BY t.txDate DESC";
        
        TypedQuery<Object[]> query = entityManager.createQuery(jpql, Object[].class);
        query.setParameter("minAmount", minAmount); // 바인딩 (Safe)
        query.setParameter("type", txType);         // 바인딩 (Safe)
        
        return query.getResultList();
    }

    /**
     * [CASE 4] JDBC Transaction Insert (거래 기록 생성)
     * 보안: 모든 입력값을 '?'로 처리하여 안전하게 삽입
     * 스키마: transactions 테이블 (tx_id, account_id, tx_type, amount, merchant_name)
     */
    public void insertTransaction(Connection conn, String txId, String accountId, String type, BigDecimal amount, String merchant) throws SQLException {
        String insertSql = "INSERT INTO transactions (tx_id, account_id, tx_type, amount, merchant_name, tx_date) " +
                           "VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)";
        
        try (PreparedStatement pstmt = conn.prepareStatement(insertSql)) {
            pstmt.setString(1, txId);
            pstmt.setString(2, accountId);
            pstmt.setString(3, type);
            pstmt.setBigDecimal(4, amount);
            pstmt.setString(5, merchant);
            
            pstmt.executeUpdate(); // 실행 (Safe)
        }
    }

    /**
     * [CASE 5] 동적 정렬 (White-list 검증)
     * 보안: 사용자가 입력한 정렬 컬럼이 허용된 리스트에 있는지 검증 후 사용
     * 스키마: accounts 테이블 (balance, created_at 등)
     */
    public void getAccountsSorted(Connection conn, String customerId, String sortColumn) throws SQLException {
        // 정렬 기준 컬럼에 대한 화이트리스트 정의
        List<String> allowedSortColumns = List.of("balance", "account_type", "created_at");
        
        // 입력값이 허용 목록에 없으면 기본값 'account_id' 사용 (SQL Injection 방어)
        String safeOrder = allowedSortColumns.contains(sortColumn) ? sortColumn : "account_id";
        
        String query = "SELECT * FROM accounts WHERE customer_id = ? ORDER BY " + safeOrder + " DESC";
        
        try (PreparedStatement pstmt = conn.prepareStatement(query)) {
            pstmt.setString(1, customerId); // 바인딩
            pstmt.executeQuery();
        }
    }
}
