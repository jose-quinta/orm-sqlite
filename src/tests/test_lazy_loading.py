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
    ManyToManyField,
    SQLiteAdapter,
    registry,
)
from src.orm.config import configure


class TestLazyLoadingBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp()
        cls.db = SQLiteAdapter(
            db_directory=cls.temp_dir,
            db_name="test_lazy",
            db_name_extension="db",
        )
        cls.db.connect()
        configure(cls.db)

        for name in list(registry.get_all().keys()):
            registry.unregister(name)

        class LazyUser(Model):
            _db = cls.db
            _table_name = "lazy_users"

            id = PrimaryKeyField()
            name = CharField(max_length=100)
            age = IntegerField(null=True)

        class LazyPost(Model):
            _db = cls.db
            _table_name = "lazy_posts"

            id = PrimaryKeyField()
            title = CharField(max_length=200)
            author = ForeignKey(LazyUser, related_name="lazy_posts")

        class LazyProfile(Model):
            _db = cls.db
            _table_name = "lazy_profiles"

            id = PrimaryKeyField()
            bio = CharField(max_length=500)
            user = OneToOneField(LazyUser, related_name="lazy_profile")

        class LazyTag(Model):
            _db = cls.db
            _table_name = "lazy_tags"

            id = PrimaryKeyField()
            name = CharField(max_length=50)

        class LazyArticle(Model):
            _db = cls.db
            _table_name = "lazy_articles"

            id = PrimaryKeyField()
            title = CharField(max_length=200)
            tags = ManyToManyField(LazyTag, related_name="articles")

        cls.User = LazyUser
        cls.Post = LazyPost
        cls.Profile = LazyProfile
        cls.Tag = LazyTag
        cls.Article = LazyArticle

        cls.User.create_table()
        cls.Post.create_table()
        cls.Profile.create_table()
        cls.Tag.create_table()
        cls.Article.create_table()

    @classmethod
    def tearDownClass(cls):
        cls.db.execute("PRAGMA foreign_keys = OFF", [])
        for m in reversed(list(registry.get_all().values())):
            try:
                m.drop_table()
            except Exception:
                pass
        cls.db.close()
        db_file = os.path.join(cls.temp_dir, "test_lazy.db")
        if os.path.exists(db_file):
            os.remove(db_file)
        os.rmdir(cls.temp_dir)

    def setUp(self):
        for name in list(registry.get_all().keys()):
            registry.unregister(name)
        for mc in [self.User, self.Post, self.Profile, self.Tag, self.Article]:
            try:
                mc.drop_table()
            except Exception:
                pass
            mc.create_table()
            registry.register(mc)

        self.alice = self.User.objects.create(name="Alice", age=30)
        self.bob = self.User.objects.create(name="Bob", age=25)

        self.post1 = self.Post.objects.create(title="Post One", author=self.alice)
        self.post2 = self.Post.objects.create(title="Post Two", author=self.alice)
        self.post3 = self.Post.objects.create(title="Post Three", author=self.bob)

        self.profile = self.Profile.objects.create(bio="Alice bio", user=self.alice)

        self.tag1 = self.Tag.objects.create(name="python")
        self.tag2 = self.Tag.objects.create(name="sql")
        self.tag3 = self.Tag.objects.create(name="orm")

        self.article1 = self.Article.objects.create(title="Article One")

        q = f"INSERT INTO {self.Article._m2m_fields['tags'].table_name} (lazy_articles_id, lazy_tags_id) VALUES (?, ?)"
        self.Article._db.execute(q, [self.article1.pk, self.tag1.pk])
        self.Article._db.execute(q, [self.article1.pk, self.tag2.pk])

    def _query_count(self, func):
        original_query = self.db.query
        count = [0]

        def counting_query(sql, params):
            count[0] += 1
            return original_query(sql, params)

        self.db.query = counting_query
        try:
            func()
        finally:
            self.db.query = original_query
        return count[0]


class TestFKForwardLazyLoading(TestLazyLoadingBase):
    def test_fk_forward_lazy_populates_cache_on_access(self):
        post = self.Post.objects.get(id=self.post1.id)
        self.assertNotIn("_author_cached", post.__dict__)
        author = post.author
        self.assertIsNotNone(author)
        self.assertIn("_author_cached", post.__dict__)
        self.assertEqual(author.name, "Alice")

    def test_fk_forward_lazy_cache_avoids_second_query(self):
        post = self.Post.objects.get(id=self.post1.id)
        queries = self._query_count(lambda: post.author)
        first_queries = queries

        queries = self._query_count(lambda: post.author)
        self.assertEqual(queries, 0, "Second access should not trigger a query")

    def test_fk_forward_lazy_returns_correct_object(self):
        post = self.Post.objects.get(id=self.post3.id)
        self.assertEqual(post.author.name, "Bob")

    def test_fk_forward_lazy_none_fk_returns_none(self):
        post = self.Post(title="Orphan")
        self.assertIsNone(post.author)

    def test_fk_forward_cache_coherence(self):
        post1 = self.Post.objects.get(id=self.post1.id)
        post3 = self.Post.objects.get(id=self.post3.id)
        self.assertEqual(post1.author.name, "Alice")
        self.assertEqual(post3.author.name, "Bob")

    def test_fk_forward_set_replaces_cache(self):
        post = self.Post.objects.get(id=self.post1.id)
        _ = post.author
        self.assertIn("_author_cached", post.__dict__)
        post.author = self.bob
        self.assertEqual(post.author.name, "Bob")


class TestFKReverseCaching(TestLazyLoadingBase):
    def test_fk_reverse_all_caches_results(self):
        user = self.User.objects.get(id=self.alice.id)
        posts = user.lazy_posts.all()
        self.assertEqual(len(posts), 2)
        self.assertIn("_lazy_posts_cached", user.__dict__)

    def test_fk_reverse_cache_uses_cached_on_second_call(self):
        user = self.User.objects.get(id=self.alice.id)
        queries = self._query_count(lambda: user.lazy_posts.all())
        first_queries = queries
        self.assertGreater(first_queries, 0)
        queries = self._query_count(lambda: user.lazy_posts.all())
        self.assertEqual(queries, 0, "Second all() should use cache")

    def test_fk_reverse_cache_returns_correct_data(self):
        user = self.User.objects.get(id=self.alice.id)
        titles = {p.title for p in user.lazy_posts.all()}
        self.assertEqual(titles, {"Post One", "Post Two"})

    def test_fk_reverse_cache_invalidates_on_create(self):
        user = self.User.objects.get(id=self.alice.id)
        _ = user.lazy_posts.all()
        self.assertIn("_lazy_posts_cached", user.__dict__)
        user.lazy_posts.create(title="New Post")
        self.assertNotIn("_lazy_posts_cached", user.__dict__)

    def test_fk_reverse_cache_invalidates_then_refreshes(self):
        user = self.User.objects.get(id=self.alice.id)
        original_count = len(user.lazy_posts.all())
        user.lazy_posts.create(title="New Post")
        new_count = len(user.lazy_posts.all())
        self.assertEqual(new_count, original_count + 1)

    def test_fk_reverse_cache_different_users_independent(self):
        alice = self.User.objects.get(id=self.alice.id)
        bob = self.User.objects.get(id=self.bob.id)
        alice_posts = alice.lazy_posts.all()
        bob_posts = bob.lazy_posts.all()
        self.assertEqual(len(alice_posts), 2)
        self.assertEqual(len(bob_posts), 1)


class TestO2OReverseCaching(TestLazyLoadingBase):
    def test_o2o_reverse_populates_cache(self):
        user = self.User.objects.get(id=self.alice.id)
        self.assertNotIn("_lazy_profile_cached", user.__dict__)
        profile = user.lazy_profile
        self.assertIsNotNone(profile)
        self.assertIn("_lazy_profile_cached", user.__dict__)
        self.assertEqual(profile.bio, "Alice bio")

    def test_o2o_reverse_cache_avoids_second_query(self):
        user = self.User.objects.get(id=self.alice.id)
        queries = self._query_count(lambda: user.lazy_profile)
        first_queries = queries
        self.assertGreater(first_queries, 0)
        queries = self._query_count(lambda: user.lazy_profile)
        self.assertEqual(queries, 0, "Second access should use cache")

    def test_o2o_reverse_cache_returns_none_when_no_profile(self):
        user = self.User.objects.get(id=self.bob.id)
        self.assertIsNone(user.lazy_profile)

    def test_o2o_reverse_cache_returns_correct_object(self):
        user = self.User.objects.get(id=self.alice.id)
        self.assertEqual(user.lazy_profile.bio, "Alice bio")


class TestM2MForwardDescriptor(TestLazyLoadingBase):
    def test_m2m_forward_returns_manager(self):
        article = self.Article.objects.get(id=self.article1.id)
        mgr = article.tags
        from src.orm.relations.related import ManyToManyForwardManager
        self.assertIsInstance(mgr, ManyToManyForwardManager)

    def test_m2m_forward_all_returns_related(self):
        article = self.Article.objects.get(id=self.article1.id)
        tags = article.tags.all()
        self.assertEqual(len(tags), 2)
        tag_names = {t.name for t in tags}
        self.assertEqual(tag_names, {"python", "sql"})

    def test_m2m_forward_all_caches_results(self):
        article = self.Article.objects.get(id=self.article1.id)
        tags = article.tags.all()
        self.assertIn("_tags_cached", article.__dict__)
        self.assertEqual(len(tags), 2)

    def test_m2m_forward_cache_avoids_second_query(self):
        article = self.Article.objects.get(id=self.article1.id)
        queries = self._query_count(lambda: article.tags.all())
        first_queries = queries
        self.assertGreater(first_queries, 0)
        queries = self._query_count(lambda: article.tags.all())
        self.assertEqual(queries, 0, "Second all() should use cache")

    def test_m2m_forward_cache_invalidates_on_add(self):
        article = self.Article.objects.get(id=self.article1.id)
        _ = article.tags.all()
        self.assertIn("_tags_cached", article.__dict__)
        article.tags.add(self.tag3)
        self.assertNotIn("_tags_cached", article.__dict__)

    def test_m2m_forward_add_then_all_includes_new(self):
        article = self.Article.objects.get(id=self.article1.id)
        article.tags.add(self.tag3)
        tag_names = {t.name for t in article.tags.all()}
        self.assertEqual(tag_names, {"python", "sql", "orm"})

    def test_m2m_forward_remove_invalidates_cache(self):
        article = self.Article.objects.get(id=self.article1.id)
        _ = article.tags.all()
        article.tags.remove(self.tag1)
        self.assertNotIn("_tags_cached", article.__dict__)

    def test_m2m_forward_remove_then_all_excludes(self):
        article = self.Article.objects.get(id=self.article1.id)
        article.tags.remove(self.tag1)
        tag_names = {t.name for t in article.tags.all()}
        self.assertEqual(tag_names, {"sql"})

    def test_m2m_forward_clear_invalidates_cache(self):
        article = self.Article.objects.get(id=self.article1.id)
        _ = article.tags.all()
        article.tags.clear()
        self.assertNotIn("_tags_cached", article.__dict__)

    def test_m2m_forward_clear_removes_all(self):
        article = self.Article.objects.get(id=self.article1.id)
        article.tags.clear()
        self.assertEqual(len(article.tags.all()), 0)


class TestPrefetchRelated(TestLazyLoadingBase):
    def test_prefetch_reverse_fk_populates_cache(self):
        users = self.User.objects.prefetch_related("lazy_posts").all()
        self.assertEqual(len(users), 2)
        for user in users:
            cache_key = "_lazy_posts_cached"
            self.assertIn(cache_key, user.__dict__)
            self.assertIsInstance(user.__dict__[cache_key], list)

    def test_prefetch_reverse_fk_correct_data(self):
        users = self.User.objects.prefetch_related("lazy_posts").all()
        user_map = {u.name: len(u.lazy_posts.all()) for u in users}
        self.assertEqual(user_map.get("Alice"), 2)
        self.assertEqual(user_map.get("Bob"), 1)

    def test_prefetch_reverse_fk_two_queries_total(self):
        queries = self._query_count(
            lambda: self.User.objects.prefetch_related("lazy_posts").all()
        )
        self.assertEqual(queries, 2)

    def test_prefetch_fk_forward_populates_cache(self):
        posts = self.Post.objects.prefetch_related("author").all()
        self.assertEqual(len(posts), 3)
        for post in posts:
            cache_key = "_author_cached"
            self.assertIn(cache_key, post.__dict__)
            self.assertIsNotNone(post.__dict__[cache_key])

    def test_prefetch_fk_forward_correct_data(self):
        posts = self.Post.objects.prefetch_related("author").all()
        author_map = {p.title: p.author.name for p in posts}
        self.assertEqual(author_map["Post One"], "Alice")
        self.assertEqual(author_map["Post Three"], "Bob")

    def test_prefetch_fk_forward_two_queries_total(self):
        queries = self._query_count(
            lambda: self.Post.objects.prefetch_related("author").all()
        )
        self.assertEqual(queries, 2)

    def test_prefetch_o2o_reverse_populates_cache(self):
        users = self.User.objects.prefetch_related("lazy_profile").all()
        for user in users:
            cache_key = "_lazy_profile_cached"
            if user.id == self.alice.id:
                self.assertIn(cache_key, user.__dict__)
            else:
                self.assertIn(cache_key, user.__dict__)

    def test_prefetch_o2o_reverse_correct_data(self):
        users = self.User.objects.prefetch_related("lazy_profile").all()
        for user in users:
            if user.id == self.alice.id:
                self.assertEqual(user.lazy_profile.bio, "Alice bio")
            else:
                self.assertIsNone(user.lazy_profile)

    def test_prefetch_m2m_forward_populates_cache(self):
        articles = self.Article.objects.prefetch_related("tags").all()
        self.assertEqual(len(articles), 1)
        self.assertIn("_tags_cached", articles[0].__dict__)
        self.assertEqual(len(articles[0].tags.all()), 2)

    def test_prefetch_m2m_forward_two_queries(self):
        queries = self._query_count(
            lambda: self.Article.objects.prefetch_related("tags").all()
        )
        self.assertEqual(queries, 3)

    def test_prefetch_m2m_reverse_populates_cache(self):
        tags = self.Tag.objects.prefetch_related("articles").all()
        self.assertEqual(len(tags), 3)
        tag_map = {t.name: t for t in tags}
        self.assertIn("_tags_cached", tag_map["python"].__dict__)
        self.assertEqual(len(tag_map["python"].articles.all()), 1)
        self.assertEqual(len(tag_map["orm"].articles.all()), 0)

    def test_prefetch_m2m_reverse_two_queries(self):
        queries = self._query_count(
            lambda: self.Tag.objects.prefetch_related("articles").all()
        )
        self.assertEqual(queries, 3)

    def test_prefetch_empty_results(self):
        for p in self.Post.objects.all():
            p.delete()
        posts = self.Post.objects.prefetch_related("author").all()
        self.assertEqual(len(posts), 0)

    def test_prefetch_filtered_with_prefetch(self):
        users = self.User.objects.filter(name="Alice").prefetch_related("lazy_posts").all()
        self.assertEqual(len(users), 1)
        self.assertEqual(len(users[0].lazy_posts.all()), 2)

    def test_prefetch_multiple_fields(self):
        users = self.User.objects.prefetch_related("lazy_posts", "lazy_profile").all()
        self.assertEqual(len(users), 2)
        for user in users:
            self.assertIn("_lazy_posts_cached", user.__dict__)
            self.assertIn("_lazy_profile_cached", user.__dict__)

    def test_prefetch_manager_access(self):
        users = self.User.objects.prefetch_related("lazy_posts").all()
        for user in users:
            posts = user.lazy_posts.all()
            self.assertIsInstance(posts, list)

    def test_prefetch_with_select_related(self):
        posts = self.Post.objects.select_related("author").prefetch_related("author").all()
        self.assertEqual(len(posts), 3)
        for post in posts:
            self.assertIn("_author_cached", post.__dict__)
            self.assertIsNotNone(post.__dict__["_author_cached"])

    def test_prefetch_via_manager(self):
        users = self.User.objects.prefetch_related("lazy_posts").all()
        self.assertEqual(len(users), 2)

    def test_prefetch_cache_hit_on_manager_all(self):
        users = self.User.objects.prefetch_related("lazy_posts").all()
        for user in users:
            cached = user.__dict__["_lazy_posts_cached"]
            results = user.lazy_posts.all()
            self.assertIs(results, cached)


if __name__ == "__main__":
    unittest.main()
