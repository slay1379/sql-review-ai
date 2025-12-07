import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

public class ValidFinancialService {

    /**
     * [Scenario 1] 단순 조회 (READ)
     * - 보안: PreparedStatement (?) 사용
     * - 성능: SELECT * 대신 필요한 컬럼(account_id, balance)만 명시
     * - 정합성: accounts 테이블과 status 컬럼 사용
     */
    public void getActiveAccountBalance(Connection conn, String customerId) throws SQLException {
        String query = "SELECT account_id, balance, account_type FROM accounts WHERE customer_id = ? AND status = 'ACTIVE'";

        try (PreparedStatement pstmt = conn.prepareStatement(query)) {
            pstmt.setString(1, customerId);

            try (ResultSet rs = pstmt.executeQuery()) {
                while (rs.next()) {
                    String accId = rs.getString("account_id");
                    BigDecimal bal = rs.getBigDecimal("balance");
                    System.out.println("Account: " + accId + ", Balance: " + bal);
                }
            }
        }
    }

    /**
     * [Scenario 2] 데이터 수정 (UPDATE)
     * - 보안: 입력받은 전화번호와 ID를 모두 바인딩 변수로 처리
     * - 정합성: customers 테이블의 PK(customer_id)를 조건으로 사용
     */
    public void updateCustomerPhone(Connection conn, String customerId, String newPhoneNumber) throws SQLException {
        String query = "UPDATE customers SET phone_number = ? WHERE customer_id = ?";

        try (PreparedStatement pstmt = conn.prepareStatement(query)) {
            pstmt.setString(1, newPhoneNumber);
            pstmt.setString(2, customerId);

            int updatedRows = pstmt.executeUpdate();
            System.out.println("Updated rows: " + updatedRows);
        }
    }

    /**
     * [Scenario 3] 조건부 목록 조회 (List SELECT)
     * - 보안: 금액(amount)과 거래유형(tx_type) 바인딩
     * - 성능: 정렬(ORDER BY)시 인덱스가 걸린 tx_date 활용 (가정)
     * - 정합성: transactions 테이블의 실제 컬럼들 사용
     */
    public void findRecentLargeTransactions(Connection conn, String accountId, BigDecimal minAmount) throws SQLException {
        String query = "SELECT tx_id, merchant_name, amount, tx_date " +
                       "FROM transactions " +
                       "WHERE account_id = ? AND amount >= ? " +
                       "ORDER BY tx_date DESC";

        try (PreparedStatement pstmt = conn.prepareStatement(query)) {
            pstmt.setString(1, accountId);
            pstmt.setBigDecimal(2, minAmount);

            try (ResultSet rs = pstmt.executeQuery()) {
                while (rs.next()) {
                    System.out.println("Tx: " + rs.getString("merchant_name") + " - " + rs.getBigDecimal("amount"));
                }
            }
        }
    }
}
