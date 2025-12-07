package com.example.demo.repository;

import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import java.util.List;

public interface GoodRepository {

    // ✅ 모범 답안: 필요한 컬럼만 명시, 대문자 사용, 스키마 준수
    @Query("""
        SELECT
            customer_id,
            name,
            email,
            phone_number
        FROM
            customers
        WHERE
            status = 'ACTIVE'
            AND created_at >= :date
    """)
    List<Object[]> findActiveCustomers(@Param("date") String date);
}
