package com.example.test;

import org.springframework.data.jpa.repository.Query;

public interface UserRepository {

    // ❌ AI가 잡아내야 할 나쁜 쿼리 (SELECT *)
    @Query("SELECT * FROM users WHERE active = 1")
    List<User> findAllActiveUsers();
}
