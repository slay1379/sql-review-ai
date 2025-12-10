package com.sh_securities.dao;

import java.sql.Connection;
import java.sql.Statement;
import java.sql.ResultSet;

public class VulnerableTransactionDAO {

    /**
     * [Bad Practice 예시]
     * - Statement 사용 및 문자열 결합 (SQL Injection 취약)
     * - SELECT * 사용 (성능 저하)
     * - 존재하지 않는 테이블(users) 참조 (스키마 환각)
     */
    public void searchUserByName(String userName) {
        
        // 1. SQL Injection 취약점: 입력값 userName을 쿼리에 바로 결합
        // 2. 스키마 불일치: 'users' 테이블은 현재 스키마 정의서에 없음 (customers가 맞음)
        // 3. 성능 이슈: SELECT * 사용 및 LIMIT 미사용
        String sql = "SELECT * FROM users WHERE name = '" + userName + "'";

        try (Connection conn = DBConnection.getConnection();
             Statement stmt = conn.createStatement()) {

            // executeQuery에 완성된 문자열을 바로 넣음 (위험!)
            ResultSet rs = stmt.executeQuery(sql);
            
            while (rs.next()) {
                // ... 로직 처리
            }
        } catch (Exception e) {
            e.printStackTrace();
        }
    }
}
