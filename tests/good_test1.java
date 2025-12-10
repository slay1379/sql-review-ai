package com.sh_securities.dao;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public class SafeTransactionDAO {

    /**
     * 특정 계좌의 최근 거래 내역을 조회합니다.
     * [Best Practice 준수]
     * - PreparedStatement 사용으로 보안 강화
     * - 필요한 컬럼만 명시하여 네트워크 부하 감소
     * - LIMIT 절을 사용하여 대량 조회 방지
     */
    public void getRecentTransactions(String accountId, String minDate, String maxDate) {
        
        // RAG 스키마에 존재하는 'transactions' 테이블 사용
        String sql = """
            SELECT 
                t.tx_id, 
                t.tx_type, 
                t.amount, 
                t.merchant_name, 
                t.tx_date 
            FROM 
                transactions t 
            WHERE 
                t.account_id = ? 
                AND t.tx_date BETWEEN ? AND ? 
            ORDER BY 
                t.tx_date DESC 
            LIMIT 50
        """;

        try (Connection conn = DBConnection.getConnection();
             PreparedStatement pstmt = conn.prepareStatement(sql)) {

            // 안전한 파라미터 바인딩
            pstmt.setString(1, accountId);
            pstmt.setString(2, minDate);
            pstmt.setString(3, maxDate);

            try (ResultSet rs = pstmt.executeQuery()) {
                while (rs.next()) {
                    System.out.println("Transaction: " + rs.getString("tx_id"));
                }
            }
        } catch (SQLException e) {
            e.printStackTrace();
        }
    }
}
