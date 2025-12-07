public class PiiTest {
    public void dangerousCode() {
        // 실제라면 절대 안 되지만 테스트를 위해 하드코딩
        String myRRN = "990101-1234567";
        String myPhone = "010-1234-5678";
        String myEmail = "admin@company.com";
        
        String query = "SELECT * FROM users WHERE rrn = '" + myRRN + "'";
    }
}
