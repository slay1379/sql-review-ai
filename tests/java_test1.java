package com.sh_securities.service;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public class TransactionDAO {

    /**
     * 특정 계좌의 최근 거래 내역(입출금/이체)을 조회합니다.
     * * [SQL Review Expectation: PASS]
     * 1. Schema Alignment: 'transactions' table (tx_id, amount, tx_date...) 사용
     * 2. Security: PreparedStatement 사용으로 SQL Injection 방지
     * 3. Performance: SELECT * 지양, LIMIT 100 사용, 인덱스 컬럼(tx_date) 활용
     */
    public void getAccountHistory(String accountId, String startDate, String endDate) {
        
        // RAG에 정의된 'transactions' 테이블 스키마에 맞춰 작성된 쿼리
        String sql = """
            SELECT 
                t.tx_id, 
                t.account_id, 
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
            LIMIT 100
        """;

        try (Connection conn = DBConnection.getConnection();
             PreparedStatement pstmt = conn.prepareStatement(sql)) {

            // 바인딩 변수 설정 (SQL Injection 방지)
            pstmt.setString(1, accountId); // account_id 매핑
            pstmt.setString(2, startDate); // 조회 시작일
            pstmt.setString(3, endDate);   // 조회 종료일

            try (ResultSet rs = pstmt.executeQuery()) {
                while (rs.next()) {
                    System.out.println("Tx ID: " + rs.getString("tx_id"));
                    System.out.println("Type: " + rs.getString("tx_type"));
                    System.out.println("Amount: " + rs.getBigDecimal("amount"));
                    // 로직 처리...
                }
            }
        } catch (SQLException e) {
            e.printStackTrace();
        }
    }
}
