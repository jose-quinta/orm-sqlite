"""
Ejemplo: Sistema de Usuarios, Roles y Permisos con Migraciones

Demuestra:
  - Modelos con relaciones FK, O2O, M2M
  - Migraciones manuales (version 001, 002)
  - Aplicar y revertir migraciones con Migrator
  - CRUD completo con usuarios, roles y permisos
  - Filtros por relaciones (rol__name, permission__codename)
"""

import sys
import hashlib
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.orm import (
    Model, PrimaryKeyField, CharField, IntegerField,
    BooleanField, DateTimeField, TextField,
    ForeignKey, OneToOneField, ManyToManyField,
    SQLiteAdapter, registry, Q, Inspector,
)
from src.orm.config import configure
from src.orm.migrations import Migration, Migrator


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


# =========================================================================
# CONFIGURACION
# =========================================================================
db = SQLiteAdapter("./data", "usuarios", "db")
db.connect()
configure(db)


# =========================================================================
# MODELOS  (orden: dependencias primero)
# =========================================================================
class Permission(Model):
    _db = db
    _table_name = "permissions"

    id = PrimaryKeyField()
    codename = CharField(max_length=100, unique=True, null=False)
    description = TextField(null=True)


class Role(Model):
    _db = db
    _table_name = "roles"

    id = PrimaryKeyField()
    name = CharField(max_length=50, unique=True, null=False)
    description = TextField(null=True)
    permissions = ManyToManyField(Permission, related_name="roles")


class User(Model):
    _db = db
    _table_name = "users"

    id = PrimaryKeyField()
    username = CharField(max_length=50, unique=True, null=False)
    email = CharField(max_length=200, unique=True, null=False)
    password_hash = CharField(max_length=64, null=False)
    is_active = BooleanField(default=True)
    created_at = DateTimeField(null=True)
    roles = ManyToManyField(Role, related_name="users")


class UserProfile(Model):
    _db = db
    _table_name = "user_profiles"

    id = PrimaryKeyField()
    full_name = CharField(max_length=150, null=True)
    bio = TextField(null=True)
    phone = CharField(max_length=20, null=True)
    birth_date = CharField(max_length=10, null=True)
    user = OneToOneField(User, related_name="profile")


# =========================================================================
# LIMPIAR EJECUCIONES ANTERIORES
# =========================================================================
db.execute("PRAGMA foreign_keys = OFF", [])
for m in reversed(list(registry.get_all().values())):
    try:
        m.drop_table()
    except Exception:
        pass
try:
    db.execute("DROP TABLE IF EXISTS __migrations__", [])
except Exception:
    pass
db.execute("PRAGMA foreign_keys = ON", [])


# =========================================================================
# MIGRACION 001: Crear tablas iniciales
# =========================================================================
class Migracion001(Migration):
    version = "001"
    description = "Crear tablas de usuarios, roles, permisos y perfiles"

    def up(self):
        self.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username VARCHAR(50) NOT NULL UNIQUE,
            email VARCHAR(200) NOT NULL UNIQUE,
            password_hash VARCHAR(64) NOT NULL,
            is_active INTEGER DEFAULT 1,
            created_at DATETIME
        )""")
        self.execute("""CREATE TABLE IF NOT EXISTS roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(50) NOT NULL UNIQUE,
            description TEXT
        )""")
        self.execute("""CREATE TABLE IF NOT EXISTS permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codename VARCHAR(100) NOT NULL UNIQUE,
            description TEXT
        )""")
        self.execute("""CREATE TABLE IF NOT EXISTS user_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name VARCHAR(150),
            bio TEXT,
            phone VARCHAR(20),
            birth_date VARCHAR(10),
            user_id INTEGER NOT NULL UNIQUE REFERENCES users(id)
        )""")
        self.execute("""CREATE TABLE IF NOT EXISTS users_roles (
            users_id INTEGER REFERENCES users(id),
            roles_id INTEGER REFERENCES roles(id),
            PRIMARY KEY (users_id, roles_id)
        )""")
        self.execute("""CREATE TABLE IF NOT EXISTS roles_permissions (
            roles_id INTEGER REFERENCES roles(id),
            permissions_id INTEGER REFERENCES permissions(id),
            PRIMARY KEY (roles_id, permissions_id)
        )""")

    def down(self):
        for t in ("users_roles", "roles_permissions", "user_profiles", "permissions", "roles", "users"):
            self.execute(f"DROP TABLE IF EXISTS {t}")


# =========================================================================
# MIGRACION 002: Agregar columna last_login a users
# =========================================================================
class Migracion002(Migration):
    version = "002"
    description = "Agregar columna last_login a users"

    def up(self):
        self.execute("ALTER TABLE users ADD COLUMN last_login DATETIME")

    def down(self):
        self.execute("ALTER TABLE users DROP COLUMN last_login")


# =========================================================================
# APLICAR MIGRACIONES
# =========================================================================
print("=== SISTEMA DE USUARIOS CON MIGRACIONES ===")
print()

migrator = Migrator(db)
migrator.add_migration(Migracion001)
migrator.add_migration(Migracion002)

print("--- Aplicando migraciones ---")
migrator.migrate()
print()

# Verificar tablas creadas
inspector = Inspector(db)
print("Tablas en la base de datos:")
for t in inspector.get_table_names():
    if not t.startswith("__"):
        print(f"  - {t}")
print()

# =========================================================================
# POBLAR DATOS INICIALES
# =========================================================================
print("--- POBLANDO DATOS INICIALES ---")

# Crear permisos
perm_create_post = Permission.objects.create(codename="create_post", description="Crear publicaciones")
perm_edit_post = Permission.objects.create(codename="edit_post", description="Editar publicaciones")
perm_delete_post = Permission.objects.create(codename="delete_post", description="Eliminar publicaciones")
perm_manage_users = Permission.objects.create(codename="manage_users", description="Gestionar usuarios")
perm_view_reports = Permission.objects.create(codename="view_reports", description="Ver reportes")

# Crear roles
admin = Role.objects.create(name="admin", description="Administrador del sistema")
mod = Role.objects.create(name="moderator", description="Moderador de contenido")
user_role = Role.objects.create(name="user", description="Usuario regular")

# Asignar permisos a roles
admin.permissions.add(perm_create_post, perm_edit_post, perm_delete_post, perm_manage_users, perm_view_reports)
mod.permissions.add(perm_create_post, perm_edit_post, perm_delete_post, perm_view_reports)
user_role.permissions.add(perm_create_post, perm_edit_post)

# Crear usuarios
alice = User.objects.create(
    username="alice",
    email="alice@sistema.com",
    password_hash=hash_password("clave123"),
)
bob = User.objects.create(
    username="bob",
    email="bob@sistema.com",
    password_hash=hash_password("segura456"),
)
admin_user = User.objects.create(
    username="admin",
    email="admin@sistema.com",
    password_hash=hash_password("admin789"),
)

# Asignar roles a usuarios
admin_user.roles.add(admin)
alice.roles.add(user_role)
bob.roles.add(user_role, mod)

# Crear perfiles
UserProfile.objects.create(user=alice, full_name="Alice Garcia", bio="Desarrolladora Python", phone="555-1001")
UserProfile.objects.create(user=bob, full_name="Bob Martinez", bio="Moderador de contenido")
UserProfile.objects.create(user=admin_user, full_name="Admin Sistema", bio="Administrador del sistema")

print(f"Usuarios: {User.objects.count()}")
print(f"Roles: {Role.objects.count()}")
print(f"Permisos: {Permission.objects.count()}")
print(f"Perfiles: {UserProfile.objects.count()}")
print()

# =========================================================================
# CONSULTAS
# =========================================================================
print("--- LISTAR USUARIOS CON SUS ROLES ---")
for u in User.objects.all():
    roles = [r.name for r in u.roles.all()]
    print(f"  @{u.username} -> roles: {roles}")

print()
print("--- PERMISOS DE CADA ROL ---")
for r in Role.objects.all():
    perms = [p.codename for p in r.permissions.all()]
    print(f"  '{r.name}': {perms}")

print()
print("--- PERFILES DE USUARIO (O2O) ---")
for u in User.objects.all():
    p = u.profile
    if p:
        print(f"  @{u.username}: {p.full_name} - {p.bio}")
    else:
        print(f"  @{u.username}: sin perfil")

print()

# =========================================================================
# FILTROS POR RELACIONES
# =========================================================================
print("--- FILTROS POR RELACIONES ---")

# Usuarios por nombre de rol
mods = User.objects.filter(roles__name="moderator").all()
print(f"Moderadores: {[u.username for u in mods]}")

# Usuarios con permiso especifico (forward: obtener usuarios que tienen rol admin)
admin_role = Role.objects.get(name="admin")
admin_users = User.objects.filter(roles__name="admin").all()
print(f"Usuarios con 'manage_users': {[u.username for u in admin_users]}")

# Usuarios activos con rol 'user'
active_users = User.objects.filter(is_active=True, roles__name="user").all()
print(f"Usuarios activos con rol 'user': {[u.username for u in active_users]}")

print()

# =========================================================================
# VERIFICAR MIGRACIONES APLICADAS
# =========================================================================
print("--- MIGRACIONES APLICADAS ---")
applied = migrator._get_applied_versions()
print(f"  Versiones: {applied}")
print()

# =========================================================================
# DEMO: REVERTIR MIGRACION 002 y VOLVER A APLICAR
# =========================================================================
print("--- DEMO: ROLLBACK y RE-APPLY MIGRACION 002 ---")

# Mostrar estado antes
cols_before = [c.name for c in inspector.get_columns("users")]
print(f"  Columnas en 'users' antes del rollback: {cols_before}")

# Rollback solo la 002
migrator.rollback(target_version="001")
cols_after_rollback = [c.name for c in inspector.get_columns("users")]
print(f"  Columnas en 'users' despues del rollback: {cols_after_rollback}")

# Volver a aplicar
migrator.migrate()
cols_after_reapply = [c.name for c in inspector.get_columns("users")]
print(f"  Columnas en 'users' despues de re-aplicar: {cols_after_reapply}")

applied_final = migrator._get_applied_versions()
print(f"  Versiones finales: {applied_final}")
print()

# =========================================================================
# LIMPIEZA
# =========================================================================
print("=== FIN DEL EJEMPLO ===")
