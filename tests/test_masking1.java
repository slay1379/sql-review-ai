package com.sh_securities.dao;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public class MaskingTestDAO {

    /**
     * 고객의 기본 정보를 조회하는 메서드
     * * [개발자 노트]
     * 테스트용 계정 정보입니다. 배포 시 삭제 요망.
     * - 테스트 대상자: 홍길동
     * - 주민등록번호: 990101-1234567  <-- [마스킹 타겟 1]
     */
    public void getUserProfile(String userId) {

        // 로컬 테스트용 하드코딩 변수 (실수로 남겨둠)
        String managerPhone = "010-1234-5678"; // <-- [마스킹 타겟 2]
        String adminEmail = "admin@shinhan.com"; // <-- [마스킹 타겟 3]

        // SQL 쿼리는 보안 수칙을 완벽하게 준수함
        String sql = """
            SELECT 
                user_id, 
                user_name, 
                grade_level, 
                last_login_at 
            FROM 
                users 
            WHERE 
                user_id = ? 
            LIMIT 1
        """;

        try (Connection conn = DBConnection.getConnection();
             PreparedStatement pstmt = conn.prepareStatement(sql)) {

            // 바인딩 처리로 SQL Injection 방지
            pstmt.setString(1, userId);

            try (ResultSet rs = pstmt.executeQuery()) {
                if (rs.next()) {
                    System.out.println("User: " + rs.getString("user_name"));
                }
            }
        } catch (SQLException e) {
            e.printStackTrace();
        }
    }
}
