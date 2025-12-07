import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

public class SafeSchemaTest {
    // ✅ 모범 답안: 
    // 1. PreparedStatement 사용 (보안 OK)
    // 2. 실제 스키마인 'customers' 테이블과 'customer_id' 컬럼 사용 (정합성 OK)
    // 3. SELECT * 대신 필요한 컬럼만 명시 (성능 OK)
    public void getCustomerSafe(Connection conn, String customerId) throws Exception {
        
        // users -> customers 로 변경
        // id -> customer_id 로 변경
        // * -> name, email 로 변경
        String query = "SELECT name, email, phone_number FROM customers WHERE customer_id = ?";
        
        PreparedStatement pstmt = conn.prepareStatement(query);
        pstmt.setString(1, customerId); 
        
        pstmt.executeQuery();
    }
}
