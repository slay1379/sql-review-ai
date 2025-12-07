import java.sql.Connection;
import java.sql.Statement;
import java.sql.ResultSet;

public class VulnerableTest {
    // ❌ 나쁜 예시: 사용자가 입력한 id를 그대로 쿼리에 붙여넣음 (SQL Injection 위험)
    public void getUser(Connection conn, String inputId) throws Exception {
        Statement stmt = conn.createStatement();
        
        // 여기에 주목! 문자열 결합(+)을 사용하고 있음
        String query = "SELECT * FROM users WHERE id = '" + inputId + "'";
        
        stmt.executeQuery(query); 
    }
}
