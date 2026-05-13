import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.orm import (
    Model,
    model,
    primary_key,
    char_field,
    integer_field,
    boolean_field,
    PrimaryKeyField,
    CharField,
    IntegerField,
    BooleanField,
    ForeignKey,
    OneToOneField,
    ManyToManyField,
    SQLiteAdapter,
    registry,
)
from src.orm.config import configure
from src.utils.logger import setup_logger


def main():
    setup_logger(level=20)

    db = SQLiteAdapter(
        db_directory="data",
        db_name="orm_example",
        db_name_extension="db",
    )
    db.connect()
    db.execute("PRAGMA foreign_keys = ON", [])

    configure(db)

    # --- Modelos con relaciones ---

    class User(Model):
        _table_name = "users"

        id = PrimaryKeyField()
        name = CharField(max_length=100, null=False)
        email = CharField(max_length=255, unique=True)
        is_active = BooleanField(default=True)

    class Post(Model):
        _table_name = "posts"

        id = PrimaryKeyField()
        title = CharField(max_length=200, null=False)
        content = CharField(max_length=1000)
        author = ForeignKey(User, related_name="posts", null=False)

    class Profile(Model):
        _table_name = "profiles"

        id = PrimaryKeyField()
        bio = CharField(max_length=500)
        user = OneToOneField(User, related_name="profile")

    @model
    class Category:
        id = primary_key()
        name = char_field(max_length=100, null=False, unique=True)

    class PostCategory(Model):
        _table_name = "post_categories"

        id = PrimaryKeyField()
        post = ForeignKey(Post, related_name="categories")
        category = ForeignKey(Category, related_name="posts")

    @model
    class Tag:
        id = primary_key()
        name = char_field(max_length=50, null=False, unique=True)

    class PostTag(Model):
        _table_name = "post_tags"

        id = PrimaryKeyField()
        post = ForeignKey(Post, related_name="tags")
        tag = ForeignKey(Tag, related_name="posts")

    print("Creating tables...")
    User.create_table()
    Post.create_table()
    Category.create_table()
    PostCategory.create_table()
    Tag.create_table()
    PostTag.create_table()

    print("Clearing existing data...")
    # Desactivar FK para poder borrar en cualquier orden
    db.execute("PRAGMA foreign_keys = OFF", [])
    for m in reversed(list(registry.get_all().values())):
        try:
            m.drop_table()
        except Exception:
            pass
    for m in registry.get_all().values():
        try:
            m.create_table()
        except Exception:
            pass
    db.execute("PRAGMA foreign_keys = ON", [])

    print("\n--- Creating users ---")
    alice = User.objects.create(name="Alice", email="alice@test.com")
    bob = User.objects.create(name="Bob", email="bob@test.com")
    print(f"  {alice}")
    print(f"  {bob}")

    print("\n--- Creating posts with FK (author=alice) ---")
    post1 = Post.objects.create(title="First Post", content="Hello!", author=alice)
    print(f"  Created: {post1}")

    post2 = Post.objects.create(title="Second Post", content="World!", author=alice)
    print(f"  Created: {post2}")

    post3 = Post.objects.create(title="Bob's Post", content="Hi!", author=bob)
    print(f"  Created: {post3}")

    print("\n--- Lazy loading: post.author ---")
    for p in Post.objects.all():
        author = p.author
        print(f"  '{p.title}' by {author.name}")

    print("\n--- Reverse relation: alice.posts.all() ---")
    for p in alice.posts.all():
        print(f"  {p.title}")

    print("\n--- Reverse relation with filter: alice.posts.filter() ---")
    for p in alice.posts.filter(title__like="First%").all():
        print(f"  {p.title}")

    print("\n--- Creating related posts via alice.posts.create() ---")
    post4 = alice.posts.create(title="Third Post", content="Created via relation")
    print(f"  Created: {post4}")

    print("\n--- OneToOne: Profile ---")
    profile = Profile.objects.create(bio="Alice's bio", user=alice)
    print(f"  Profile: {profile}")
    print(f"  Profile user: {profile.user.name}")
    print(f"  Alice profile: {alice.profile}")

    print("\n--- ManyToMany via intermediate table ---")
    tech = Category.objects.create(name="Tech")
    life = Category.objects.create(name="Lifestyle")

    PostCategory.objects.create(post=post1, category=tech)
    PostCategory.objects.create(post=post2, category=tech)
    PostCategory.objects.create(post=post2, category=life)

    print("  Post 1 categories:")
    for pc in PostCategory.objects.filter(post_id=post1.id).all():
        print(f"    {pc.category.name}")

    print("\n--- Tags with M2M helper ---")
    python = Tag.objects.create(name="python")
    sqlite = Tag.objects.create(name="sqlite")

    PostTag.objects.create(post=post1, tag=python)
    PostTag.objects.create(post=post1, tag=sqlite)
    PostTag.objects.create(post=post2, tag=python)

    print("  Post 1 tags:")
    for pt in PostTag.objects.filter(post_id=post1.id).all():
        print(f"    {pt.tag.name}")

    print("\nRegistered models:")
    for name in registry.get_all():
        print(f"  {name}")

    db.close()


if __name__ == "__main__":
    main()
