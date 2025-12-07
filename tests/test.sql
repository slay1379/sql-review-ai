import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

public class VulnerableTest {
    // ✅ 좋은 예시: PreparedStatement를 사용하여 파라미터 바인딩 (?)
    public void getUser(Connection conn, String inputId) throws Exception {
        
        // 문자열 결합 대신 ? 를 사용
        String query = "SELECT * FROM users WHERE id = ?";
        
        PreparedStatement pstmt = conn.prepareStatement(query);
        pstmt.setString(1, inputId); // 안전하게 값 주입
        
        pstmt.executeQuery();
    }
}
