package com.example.demo.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import java.util.List;

public interface TestMixedRepository extends JpaRepository<Object, Long> {

    @Query("SELECT customer_id, name, email FROM customers WHERE customer_id = :id")
    List<Object[]> findCustomerCorrectly(@Param("id") String id);

    @Query("SELECT * FROM customers WHERE status = 'ACTIVE'")
    List<Object> findAllActiveCustomersBad();

    @Query("SELECT username, password FROM users WHERE id = :id")
    List<Object[]> findNonExistentUser(@Param("id") Long id);

    @Query(value = "select customer_id, name from customers where created_at > now()", nativeQuery = true)
    List<Object[]> findRecentCustomersMessy();
}
