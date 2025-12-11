package com.sh_securities.service;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public class TransactionDAO {

    /**
     * 특정 고객의 최근 거래 내역을 조회합니다.
     * * [SQL Review Check Points]
     * - Parameter Binding: OK (PreparedStatement used)
     * - Select Specific Columns: OK (No SELECT *)
     * - Limit Clause: OK
     */
    public void getRecentTrades(String userId, String startDate, String endDate) {
        
        // 쿼리 가독성을 위해 Text Block 사용
        String sql = """
            SELECT 
                t.trade_id, 
                t.account_number, 
                t.stock_code, 
                t.trade_type, 
                t.quantity, 
                t.price, 
                t.trade_time 
            FROM 
                trade_history t 
            WHERE 
                t.user_id = ? 
                AND t.trade_time BETWEEN ? AND ? 
            ORDER BY 
                t.trade_time DESC 
            LIMIT 100
        """;

        try (Connection conn = DBConnection.getConnection();
             PreparedStatement pstmt = conn.prepareStatement(sql)) {

            // 바인딩 변수 설정 (SQL Injection 방지)
            pstmt.setString(1, userId);
            pstmt.setString(2, startDate);
            pstmt.setString(3, endDate);

            try (ResultSet rs = pstmt.executeQuery()) {
                while (rs.next()) {
                    System.out.println("Trade ID: " + rs.getString("trade_id"));
                    // 로직 처리...
                }
            }
        } catch (SQLException e) {
            e.printStackTrace();
        }
    }
}
