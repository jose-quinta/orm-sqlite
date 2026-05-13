import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import unittest
from src.orm.query_builder import (
    Select, Condition, RawCondition, Where,
    Join, OrderBy, Limit, Offset, CompiledQuery,
    QueryBuilder,
)


class TestSelect(unittest.TestCase):
    def test_default_all_columns(self):
        s = Select()
        self.assertEqual(s.compile(), "*")

    def test_with_columns(self):
        s = Select(["id", "name"])
        self.assertEqual(s.compile(), "id, name")

    def test_add_column(self):
        s = Select(["id"])
        s.add_column("name")
        self.assertEqual(s.compile(), "id, name")

    def test_empty_list(self):
        s = Select([])
        self.assertEqual(s.compile(), "*")


class TestCondition(unittest.TestCase):
    def test_equals(self):
        c = Condition("name", "=", "Alice")
        sql, params = c.compile()
        self.assertEqual(sql, "name = ?")
        self.assertEqual(params, ["Alice"])

    def test_greater_than(self):
        c = Condition("age", ">", 25)
        sql, params = c.compile()
        self.assertEqual(sql, "age > ?")
        self.assertEqual(params, [25])

    def test_in(self):
        c = Condition("id", "IN", [1, 2, 3])
        sql, params = c.compile()
        self.assertEqual(sql, "id IN (?, ?, ?)")
        self.assertEqual(params, [1, 2, 3])

    def test_in_single(self):
        c = Condition("id", "IN", [1])
        sql, params = c.compile()
        self.assertEqual(sql, "id IN (?)")
        self.assertEqual(params, [1])


class TestRawCondition(unittest.TestCase):
    def test_raw_sql(self):
        rc = RawCondition("age > ?", [18])
        sql, params = rc.compile()
        self.assertEqual(sql, "age > ?")
        self.assertEqual(params, [18])

    def test_no_params(self):
        rc = RawCondition("1 = 1")
        sql, params = rc.compile()
        self.assertEqual(sql, "1 = 1")
        self.assertEqual(params, [])


class TestWhere(unittest.TestCase):
    def test_empty(self):
        w = Where()
        sql, params = w.compile()
        self.assertEqual(sql, "")
        self.assertEqual(params, [])

    def test_single_condition(self):
        w = Where()
        w.add("name", "=", "Alice")
        sql, params = w.compile()
        self.assertEqual(sql, "name = ?")
        self.assertEqual(params, ["Alice"])

    def test_multiple_and(self):
        w = Where()
        w.add("name", "=", "Alice")
        w.add("age", ">", 25)
        sql, params = w.compile()
        self.assertEqual(sql, "name = ? AND age > ?")
        self.assertEqual(params, ["Alice", 25])

    def test_or_connector(self):
        w = Where(connector="OR")
        w.add("name", "=", "Alice")
        w.add("name", "=", "Bob")
        sql, params = w.compile()
        self.assertEqual(sql, "name = ? OR name = ?")
        self.assertEqual(params, ["Alice", "Bob"])

    def test_nested_where_or(self):
        w = Where("AND")
        w.add("is_active", "=", True)

        sub = Where("OR")
        sub.add("name", "=", "Alice")
        sub.add("age", "<", 18)
        w.add_where(sub)

        sql, params = w.compile()
        self.assertEqual(sql, "is_active = ? AND (name = ? OR age < ?)")
        self.assertEqual(params, [True, "Alice", 18])

    def test_add_raw(self):
        w = Where()
        w.add("name", "=", "Alice")
        w.add_raw("age IN (SELECT id FROM ...)")
        sql, params = w.compile()
        self.assertEqual(sql, "name = ? AND age IN (SELECT id FROM ...)")
        self.assertEqual(params, ["Alice"])

    def test_multiple_nested(self):
        w = Where("AND")
        sub1 = Where("OR")
        sub1.add("name", "=", "Alice")
        sub1.add("name", "=", "Bob")

        sub2 = Where("OR")
        sub2.add("age", ">", 30)
        sub2.add("is_active", "=", False)

        w.add_where(sub1)
        w.add_where(sub2)

        sql, params = w.compile()
        self.assertIn("(name = ? OR name = ?)", sql)
        self.assertIn("(age > ? OR is_active = ?)", sql)
        self.assertIn("AND", sql)


class TestJoin(unittest.TestCase):
    def test_left_join(self):
        j = Join("users", on=["posts.author_id", "=", "users.id"], alias="u")
        sql = j.compile()
        self.assertEqual(sql, "LEFT JOIN users AS u ON posts.author_id = users.id")

    def test_inner_join(self):
        j = Join("users", on=["p.author_id", "=", "u.id"], type="INNER")
        sql = j.compile()
        self.assertEqual(sql, "INNER JOIN users ON p.author_id = u.id")

    def test_no_alias(self):
        j = Join("users", on=["a", "=", "b"])
        sql = j.compile()
        self.assertEqual(sql, "LEFT JOIN users ON a = b")

    def test_raw_on(self):
        j = Join("users", on="posts.author_id = users.id")
        sql = j.compile()
        self.assertEqual(sql, "LEFT JOIN users ON posts.author_id = users.id")


class TestOrderBy(unittest.TestCase):
    def test_empty(self):
        o = OrderBy()
        self.assertEqual(o.compile(), "")

    def test_single_field(self):
        o = OrderBy(["name"])
        self.assertEqual(o.compile(), "name")

    def test_multiple_fields(self):
        o = OrderBy(["age DESC", "name ASC"])
        self.assertEqual(o.compile(), "age DESC, name ASC")

    def test_add_field(self):
        o = OrderBy()
        o.add("age", "DESC")
        o.add("name")
        self.assertEqual(o.compile(), "age DESC, name")

    def test_add_without_direction(self):
        o = OrderBy()
        o.add("name")
        self.assertEqual(o.compile(), "name")


class TestLimit(unittest.TestCase):
    def test_value(self):
        l = Limit(10)
        self.assertEqual(l.value, 10)


class TestOffset(unittest.TestCase):
    def test_value(self):
        o = Offset(5)
        self.assertEqual(o.value, 5)


class TestCompiledQuery(unittest.TestCase):
    def test_basic(self):
        cq = CompiledQuery("SELECT * FROM users WHERE id = ?", [1])
        self.assertEqual(cq.sql, "SELECT * FROM users WHERE id = ?")
        self.assertEqual(cq.params, [1])

    def test_default_params(self):
        cq = CompiledQuery("SELECT 1")
        self.assertEqual(cq.params, [])




class MockModel:
    _table_name = "users"


class TestQueryBuilder(unittest.TestCase):
    def setUp(self):
        self.builder = QueryBuilder(MockModel)

    def test_select_default(self):
        cq = self.builder.compile()
        self.assertEqual(cq.sql, "SELECT * FROM users")
        self.assertEqual(cq.params, [])

    def test_select_columns(self):
        cq = self.builder.select("id", "name").compile()
        self.assertEqual(cq.sql, "SELECT id, name FROM users")

    def test_add_select(self):
        cq = self.builder.add_select("id").add_select("name").compile()
        self.assertEqual(cq.sql, "SELECT id, name FROM users")

    def test_where_equals(self):
        cq = self.builder.where(name="Alice").compile()
        self.assertEqual(cq.sql, "SELECT * FROM users WHERE name = ?")
        self.assertEqual(cq.params, ["Alice"])

    def test_where_multiple_and(self):
        cq = self.builder.where(name="Alice", age=30).compile()
        self.assertEqual(cq.sql, "SELECT * FROM users WHERE name = ? AND age = ?")
        self.assertEqual(cq.params, ["Alice", 30])

    def test_where_gt(self):
        cq = self.builder.where(age__gt=25).compile()
        self.assertEqual(cq.sql, "SELECT * FROM users WHERE age > ?")
        self.assertEqual(cq.params, [25])

    def test_where_gte(self):
        cq = self.builder.where(age__gte=25).compile()
        self.assertEqual(cq.sql, "SELECT * FROM users WHERE age >= ?")
        self.assertEqual(cq.params, [25])

    def test_where_lt(self):
        cq = self.builder.where(age__lt=30).compile()
        self.assertEqual(cq.sql, "SELECT * FROM users WHERE age < ?")
        self.assertEqual(cq.params, [30])

    def test_where_lte(self):
        cq = self.builder.where(age__lte=30).compile()
        self.assertEqual(cq.sql, "SELECT * FROM users WHERE age <= ?")
        self.assertEqual(cq.params, [30])

    def test_where_ne(self):
        cq = self.builder.where(name__ne="Alice").compile()
        self.assertEqual(cq.sql, "SELECT * FROM users WHERE name != ?")
        self.assertEqual(cq.params, ["Alice"])

    def test_where_like(self):
        cq = self.builder.where(name__like="Ali%").compile()
        self.assertEqual(cq.sql, "SELECT * FROM users WHERE name LIKE ?")
        self.assertEqual(cq.params, ["Ali%"])

    def test_where_in(self):
        cq = self.builder.where(id__in=[1, 2, 3]).compile()
        self.assertEqual(cq.sql, "SELECT * FROM users WHERE id IN (?, ?, ?)")
        self.assertEqual(cq.params, [1, 2, 3])

    def test_where_in_single(self):
        cq = self.builder.where(id__in=[1]).compile()
        self.assertEqual(cq.sql, "SELECT * FROM users WHERE id IN (?)")
        self.assertEqual(cq.params, [1])

    def test_where_raw_sql(self):
        cq = self.builder.where("age > ?", [18]).compile()
        self.assertEqual(cq.sql, "SELECT * FROM users WHERE age > ?")
        self.assertEqual(cq.params, [18])

    def test_where_raw_no_params(self):
        cq = self.builder.where("is_active = 1").compile()
        self.assertEqual(cq.sql, "SELECT * FROM users WHERE is_active = 1")
        self.assertEqual(cq.params, [])

    def test_where_chained(self):
        cq = (
            self.builder
            .where(name="Alice")
            .where(age__gt=25)
            .compile()
        )
        self.assertEqual(cq.sql, "SELECT * FROM users WHERE name = ? AND age > ?")
        self.assertEqual(cq.params, ["Alice", 25])

    def test_join_left(self):
        cq = (
            self.builder
            .join("posts", on=["users.id", "=", "posts.user_id"], alias="p")
            .compile()
        )
        self.assertEqual(
            cq.sql,
            "SELECT * FROM users LEFT JOIN posts AS p ON users.id = posts.user_id",
        )

    def test_join_inner(self):
        cq = (
            self.builder
            .join("posts", on=["u.id", "=", "p.user_id"], alias="p", type="INNER")
            .compile()
        )
        self.assertEqual(
            cq.sql,
            "SELECT * FROM users INNER JOIN posts AS p ON u.id = p.user_id",
        )

    def test_join_with_where(self):
        cq = (
            self.builder
            .join("posts", on=["users.id", "=", "posts.user_id"], alias="p")
            .where("p.title = ?", ["Hello"])
            .compile()
        )
        self.assertEqual(
            cq.sql,
            "SELECT * FROM users LEFT JOIN posts AS p ON users.id = posts.user_id WHERE p.title = ?",
        )
        self.assertEqual(cq.params, ["Hello"])

    def test_join_with_where_kwargs(self):
        cq = (
            self.builder
            .join("posts", on=["users.id", "=", "posts.user_id"], alias="p")
            .where(title="Hello")
            .compile()
        )
        self.assertEqual(
            cq.sql,
            "SELECT * FROM users LEFT JOIN posts AS p ON users.id = posts.user_id WHERE title = ?",
        )

    def test_order_by_single(self):
        cq = self.builder.order_by("name").compile()
        self.assertEqual(cq.sql, "SELECT * FROM users ORDER BY name")

    def test_order_by_multiple(self):
        cq = self.builder.order_by("age DESC", "name ASC").compile()
        self.assertEqual(cq.sql, "SELECT * FROM users ORDER BY age DESC, name ASC")

    def test_order_by_chained(self):
        cq = self.builder.order_by("age DESC").order_by("name").compile()
        self.assertEqual(cq.sql, "SELECT * FROM users ORDER BY age DESC, name")

    def test_limit(self):
        cq = self.builder.limit(10).compile()
        self.assertEqual(cq.sql, "SELECT * FROM users LIMIT 10")

    def test_offset(self):
        cq = self.builder.offset(5).compile()
        self.assertEqual(cq.sql, "SELECT * FROM users OFFSET 5")

    def test_limit_with_offset(self):
        cq = self.builder.limit(10).offset(5).compile()
        self.assertEqual(cq.sql, "SELECT * FROM users LIMIT 10 OFFSET 5")

    def test_full_query(self):
        cq = (
            self.builder
            .select("u.id", "u.name", "p.title")
            .join("posts", on=["u.id", "=", "p.user_id"], alias="p")
            .where("u.is_active = ? AND p.title LIKE ?", [True, "%Post"])
            .order_by("u.name")
            .limit(5)
            .offset(10)
            .compile()
        )
        self.assertEqual(
            cq.sql,
            "SELECT u.id, u.name, p.title FROM users"
            " LEFT JOIN posts AS p ON u.id = p.user_id"
            " WHERE u.is_active = ? AND p.title LIKE ?"
            " ORDER BY u.name LIMIT 5 OFFSET 10",
        )
        self.assertEqual(cq.params, [True, "%Post"])

    def test_builder_is_reusable(self):
        cq1 = self.builder.where(name="Alice").compile()
        cq2 = self.builder.compile()
        self.assertEqual(cq1.sql, cq2.sql)
        self.assertEqual(cq1.params, cq2.params)


if __name__ == "__main__":
    unittest.main()
