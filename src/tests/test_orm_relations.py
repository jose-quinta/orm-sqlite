import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import unittest
import os
import tempfile
from src.orm import (
    Model,
    PrimaryKeyField,
    CharField,
    IntegerField,
    ForeignKey,
    OneToOneField,
    SQLiteAdapter,
    registry,
)
from src.orm.config import configure


class TestSelectRelated(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp()
        cls.db = SQLiteAdapter(
            db_directory=cls.temp_dir,
            db_name="test_select_related",
            db_name_extension="db",
        )
        cls.db.connect()
        configure(cls.db)

        for name in list(registry.get_all().keys()):
            registry.unregister(name)

        class RelUser(Model):
            _db = cls.db
            _table_name = "rel_users"

            id = PrimaryKeyField()
            name = CharField(max_length=100, null=False)
            age = IntegerField(null=True)

        class RelPost(Model):
            _db = cls.db
            _table_name = "rel_posts"

            id = PrimaryKeyField()
            title = CharField(max_length=200, null=False)
            author = ForeignKey(RelUser, related_name="rel_posts")

        cls.User = RelUser
        cls.Post = RelPost

        cls.User.create_table()
        cls.Post.create_table()

    @classmethod
    def tearDownClass(cls):
        cls.db.execute("PRAGMA foreign_keys = OFF", [])
        for m in reversed(list(registry.get_all().values())):
            try:
                m.drop_table()
            except Exception:
                pass
        cls.db.close()
        db_file = os.path.join(cls.temp_dir, "test_select_related.db")
        if os.path.exists(db_file):
            os.remove(db_file)
        os.rmdir(cls.temp_dir)

    def setUp(self):
        for name in list(registry.get_all().keys()):
            registry.unregister(name)
            try:
                m = self.User if name == "RelUser" else self.Post
                m.drop_table()
                m.create_table()
            except Exception:
                pass

        registry.register(self.User)
        registry.register(self.Post)
        self.User.create_table()
        self.Post.create_table()

        self.alice = self.User.objects.create(name="Alice", age=30)
        self.bob = self.User.objects.create(name="Bob", age=25)
        self.post1 = self.Post.objects.create(title="Post One", author=self.alice)
        self.post2 = self.Post.objects.create(title="Post Two", author=self.alice)
        self.post3 = self.Post.objects.create(title="Post Three", author=self.bob)

    def test_select_related_populates_cache(self):
        posts = self.Post.objects.select_related("author").all()
        self.assertEqual(len(posts), 3)
        for p in posts:
            cache_key = "_author_cached"
            self.assertIn(cache_key, p.__dict__)
            self.assertIsNotNone(p.__dict__[cache_key])

    def test_select_related_returns_correct_objects(self):
        posts = self.Post.objects.select_related("author").all()
        author_map = {p.title: p.author.name for p in posts}
        self.assertEqual(author_map["Post One"], "Alice")
        self.assertEqual(author_map["Post Two"], "Alice")
        self.assertEqual(author_map["Post Three"], "Bob")

    def test_select_related_no_extra_queries(self):
        posts = self.Post.objects.select_related("author").all()
        for p in posts:
            _ = p.author
        for p in posts:
            cache_key = f"_author_cached"
            self.assertIn(cache_key, p.__dict__)

    def test_select_related_empty_result(self):
        for p in self.Post.objects.all():
            p.delete()
        posts = self.Post.objects.select_related("author").all()
        self.assertEqual(len(posts), 0)

    def test_select_related_via_manager(self):
        posts = self.Post.objects.select_related("author").all()
        self.assertEqual(len(posts), 3)

    def test_without_select_related_no_cache(self):
        posts = self.Post.objects.all()
        for p in posts:
            cache_key = "_author_cached"
            self.assertNotIn(cache_key, p.__dict__)

    def test_select_related_generates_join(self):
        qs = self.Post.objects.select_related("author")
        compiled = qs._builder.compile()
        self.assertIn("LEFT JOIN", compiled.sql)
        self.assertIn("__author", compiled.sql)
        self.assertIn("rel_users", compiled.sql)
        self.assertNotIn("*", compiled.sql)

    def test_select_related_single_query(self):
        posts = self.Post.objects.select_related("author").all()
        for p in posts:
            author = p.author
            self.assertIsNotNone(author)
            self.assertIn("_author_cached", p.__dict__)


class TestRelationFilterTraversal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp()
        cls.db = SQLiteAdapter(
            db_directory=cls.temp_dir,
            db_name="test_rel_filter",
            db_name_extension="db",
        )
        cls.db.connect()
        configure(cls.db)

        for name in list(registry.get_all().keys()):
            registry.unregister(name)

        class UserRel(Model):
            _db = cls.db
            _table_name = "users_rel"

            id = PrimaryKeyField()
            name = CharField(max_length=100, null=False)
            age = IntegerField(null=True)

        class PostRel(Model):
            _db = cls.db
            _table_name = "posts_rel"

            id = PrimaryKeyField()
            title = CharField(max_length=200, null=False)
            author = ForeignKey(UserRel, related_name="posts_rel")

        class ProfileRel(Model):
            _db = cls.db
            _table_name = "profiles_rel"

            id = PrimaryKeyField()
            bio = CharField(max_length=500)
            user = OneToOneField(UserRel, related_name="profile_rel")

        cls.User = UserRel
        cls.Post = PostRel
        cls.Profile = ProfileRel

        cls.User.create_table()
        cls.Post.create_table()
        cls.Profile.create_table()

    @classmethod
    def tearDownClass(cls):
        cls.db.execute("PRAGMA foreign_keys = OFF", [])
        for m in reversed(list(registry.get_all().values())):
            try:
                m.drop_table()
            except Exception:
                pass
        cls.db.close()
        db_file = os.path.join(cls.temp_dir, "test_rel_filter.db")
        if os.path.exists(db_file):
            os.remove(db_file)
        os.rmdir(cls.temp_dir)

    def setUp(self):
        for name in list(registry.get_all().keys()):
            registry.unregister(name)
        for model_cls in [self.User, self.Post, self.Profile]:
            try:
                model_cls.drop_table()
            except Exception:
                pass
            model_cls.create_table()
            registry.register(model_cls)

        self.alice = self.User.objects.create(name="Alice", age=30)
        self.bob = self.User.objects.create(name="Bob", age=25)
        self.charlie = self.User.objects.create(name="Charlie", age=35)

        self.post1 = self.Post.objects.create(title="Alice Post", author=self.alice)
        self.post2 = self.Post.objects.create(title="Bob Post", author=self.bob)
        self.post3 = self.Post.objects.create(title="Charlie Post", author=self.charlie)

        self.profile = self.Profile.objects.create(bio="Alice bio", user=self.alice)

    def test_filter_by_fk_field(self):
        results = self.Post.objects.filter(author__name="Alice").all()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, "Alice Post")

    def test_filter_by_fk_with_operator(self):
        results = self.Post.objects.filter(author__age__gt=28).all()
        self.assertEqual(len(results), 2)
        titles = {p.title for p in results}
        self.assertIn("Alice Post", titles)
        self.assertIn("Charlie Post", titles)

    def test_filter_by_fk_with_ne(self):
        results = self.Post.objects.filter(author__name__ne="Alice").all()
        self.assertEqual(len(results), 2)

    def test_filter_by_fk_with_like(self):
        results = self.Post.objects.filter(author__name__like="Ali%").all()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, "Alice Post")

    def test_filter_by_fk_with_in(self):
        results = self.Post.objects.filter(author__age__in=[25, 35]).all()
        self.assertEqual(len(results), 2)
        titles = {p.title for p in results}
        self.assertIn("Bob Post", titles)
        self.assertIn("Charlie Post", titles)

    def test_filter_by_fk_with_pk(self):
        results = self.Post.objects.filter(author__pk=self.alice.pk).all()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, "Alice Post")

    def test_filter_by_fk_chained_with_normal_filter(self):
        results = (
            self.Post.objects
            .filter(author__name="Alice")
            .filter(title__like="%Post")
            .all()
        )
        self.assertEqual(len(results), 1)

    def test_exclude_by_fk(self):
        results = self.Post.objects.exclude(author__name="Alice").all()
        self.assertEqual(len(results), 2)

    def test_filter_by_o2o_field(self):
        results = self.User.objects.filter(profile_rel__bio="Alice bio").all()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "Alice")

    def test_filter_by_fk_no_results(self):
        results = self.Post.objects.filter(author__name="Nobody").all()
        self.assertEqual(len(results), 0)


class TestQuerySetJoin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp()
        cls.db = SQLiteAdapter(
            db_directory=cls.temp_dir,
            db_name="test_qs_join",
            db_name_extension="db",
        )
        cls.db.connect()
        configure(cls.db)

        for name in list(registry.get_all().keys()):
            registry.unregister(name)

        class Author(Model):
            _db = cls.db
            _table_name = "authors"

            id = PrimaryKeyField()
            name = CharField(max_length=100)

        class Book(Model):
            _db = cls.db
            _table_name = "books"

            id = PrimaryKeyField()
            title = CharField(max_length=200)
            author = ForeignKey(Author, related_name="books")

        cls.Author = Author
        cls.Book = Book
        cls.Author.create_table()
        cls.Book.create_table()

    @classmethod
    def tearDownClass(cls):
        cls.db.execute("PRAGMA foreign_keys = OFF", [])
        for m in reversed(list(registry.get_all().values())):
            try:
                m.drop_table()
            except Exception:
                pass
        cls.db.close()
        db_file = os.path.join(cls.temp_dir, "test_qs_join.db")
        if os.path.exists(db_file):
            os.remove(db_file)
        os.rmdir(cls.temp_dir)

    def setUp(self):
        for name in list(registry.get_all().keys()):
            registry.unregister(name)
        for mc in [self.Author, self.Book]:
            try:
                mc.drop_table()
            except Exception:
                pass
            mc.create_table()
            registry.register(mc)

        self.a1 = self.Author.objects.create(name="Alice")
        self.a2 = self.Author.objects.create(name="Bob")
        self.b1 = self.Book.objects.create(title="Book A1", author=self.a1)
        self.b2 = self.Book.objects.create(title="Book A2", author=self.a1)
        self.b3 = self.Book.objects.create(title="Book B1", author=self.a2)

    def test_join_fk(self):
        qs = self.Book.objects.join("author")
        self.assertIsNotNone(qs)
        self.assertEqual(len(qs._builder._joins), 1)

    def test_join_and_all(self):
        self.assertEqual(len(self.Book.objects.all()), 3)

    def test_select_custom_columns(self):
        from src.orm.query_builder import CompiledQuery

        qs = self.Book.objects.select("id", "title")
        cq = qs._builder.compile()
        self.assertIn("SELECT id, title", cq.sql)
        self.assertIn("FROM books", cq.sql)

    def test_join_via_manager(self):
        qs = self.Book.objects.join("author")
        results = qs.all()
        self.assertEqual(len(results), 3)


if __name__ == "__main__":
    unittest.main()
