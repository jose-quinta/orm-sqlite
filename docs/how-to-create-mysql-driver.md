# Cómo Crear un Driver MySQL desde Cero en Python

## Guía conceptual y paso a paso para implementar un driver de base de datos

---

## 1. Introducción

Un **driver de base de datos** es una biblioteca que implementa el protocolo de comunicación con un motor de base de datos específico. Permite que programas en Python (u otros lenguajes) envíen consultas SQL y reciban resultados sin conocer los detalles del protocolo binario subyacente.

### ¿Qué hace un driver?

```
App Python                    Driver                      Servidor MySQL
    │                           │                              │
    │  cursor.execute(sql)      │                              │
    │ ─────────────────────────►│                              │
    │                           │  Paquete TCP (COM_QUERY)     │
    │                           │ ────────────────────────────►│
    │                           │                              │
    │                           │  Paquetes de respuesta       │
    │                           │ ◄────────────────────────────│
    │  filas = cursor.fetchall()│                              │
    │ ◄─────────────────────────│                              │
```

### PEP 249 — Python DB-API 2.0

La mayoría de los drivers Python siguen la especificación **PEP 249** que define una interfaz estándar:

- `connect(host, port, user, password, database)` → objeto `Connection`
- `Connection.cursor()` → objeto `Cursor`
- `Cursor.execute(query, params)` → ejecuta SQL
- `Cursor.fetchone()` / `fetchall()` → obtiene resultados
- `Cursor.description` → metadatos de columnas
- `Connection.commit()` / `rollback()` / `close()`

---

## 2. Arquitectura General de un Driver

```
┌──────────────────────────────────────────────────────────────┐
│                       API Pública (PEP 249)                   │
│  connect() │ Connection │ Cursor │ execute │ fetchall        │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│                  Capa de Protocolo                            │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐    │
│  │ Handshake/  │  │ Query Packet │  │ Result Set       │    │
│  │ Auth        │  │ Builder      │  │ Parser           │    │
│  └─────────────┘  └──────────────┘  └──────────────────┘    │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│                  Capa de Transporte                           │
│  socket TCP ──► bufferización ──► enviar/recibir paquetes    │
└──────────────────────────────────────────────────────────────┘
                           │
                           ▼
                  Servidor MySQL (puerto 3306)
```

---

## 3. Fase 1: El Protocolo de MySQL

MySQL tiene un **protocolo binario** sobre TCP/IP. Se divide en fases:

### 3.1 Handshake Inicial

Cuando un cliente se conecta, el servidor envía un **HandshakeV10**:

```
Servidor ──► Cliente:  Packet #1 (HandshakeV10)
  ├── protocol_version  (0x0a = 10)
  ├── server_version    (string, ej: "8.0.33")
  ├── connection_id     (4 bytes)
  ├── auth_plugin_data  (scramble, 8 + 12 bytes)
  ├── capability_flags  (qué funciones soporta el servidor)
  ├── character_set     (código de charset)
  ├── status_flags      (SERVER_STATUS_AUTOCOMMIT, etc.)
  └── auth_plugin_name  (ej: "caching_sha2_password")
```

### 3.2 Autenticación

El cliente responde con un paquete de autenticación:

```
Cliente ──► Servidor: Packet (Login)
  ├── client_capabilities
  ├── max_packet_size
  ├── character_set
  ├── username
  ├── auth_response = SHA256(password) XOR scramble    ← depende del plugin
  ├── database (opcional)
  └── auth_plugin_name
```

MySQL 8.0 usa por defecto `caching_sha2_password`. El flujo es:

1. Cliente calcula `SHA256(SHA256(password)) XOR SHA256(scramble + SHA256(SHA256(password)))`
2. Servidor verifica
3. Si el servidor no tiene el hash en caché, puede solicitar un intercambio adicional de clave pública (RSA)

### 3.3 Intercambio de Paquetes

Cada paquete MySQL tiene esta estructura:

```
┌─────────────────────────────────────────────────────────┐
│ 3 bytes: payload_length    (longitud del cuerpo)        │
│ 1 byte:  sequence_id       (contador, 0-255)            │
│ N bytes: payload           (datos del comando)          │
└─────────────────────────────────────────────────────────┘
```

**Límite**: Cada paquete tiene máximo 16MB. Paquetes mayores se dividen en **paquetes múltiples** (todos con `payload_length = 0xffffff` excepto el último).

### 3.4 Comandos (Command Packets)

```
Payload del comando:
  ┌─────────┬──────────────────────┐
  │ 1 byte  │ command              │
  │ N bytes │ command arguments    │
  └─────────┴──────────────────────┘

Command IDs:
  0x00 → COM_SLEEP
  0x01 → COM_QUIT
  0x02 → COM_INIT_DB
  0x03 → COM_QUERY            ← el más importante
  0x04 → COM_FIELD_LIST
  0x05 → COM_CREATE_DB
  0x06 → COM_DROP_DB
  0x07 → COM_REFRESH
  0x08 → COM_SHUTDOWN
  0x09 → COM_STATISTICS
  0x10 → COM_PING
  0x11 → COM_STMT_PREPARE
  0x12 → COM_STMT_EXECUTE
  0x13 → COM_STMT_CLOSE
  0x14 → COM_STMT_FETCH
  0x1e → COM_RESET_CONNECTION
```

### 3.5 Paquete de Respuesta

El servidor responde con uno de estos tipos:

```
Primer byte del payload:
  0x00 → OK packet        (comando exitoso sin filas)
  0xff → ERR packet       (error)
  0xfe → EOF packet       (fin de resultados, en protocolo antiguo)
          o Auth Switch   (durante autenticación)
  0x01 → Number of rows   (para resultados con filas, ej: SELECT)
```

**OK Packet** (para INSERT/UPDATE/DELETE):

```
┌─────────┬────────────────────────────────────┐
│ 1 byte  │ 0x00 (OK)                          │
│ 1-9 var │ affected_rows                      │
│ 1-9 var │ last_insert_id                     │
│ 2 bytes │ status_flags                       │
│ 2 bytes │ warnings                           │
│ ...     │ info (mensaje opcional)            │
└─────────┴────────────────────────────────────┘
```

**ERR Packet**:

```
┌─────────┬────────────────────────────────────┐
│ 1 byte  │ 0xff                               │
│ 2 bytes │ error_code                         │
│ 1 byte  │ '#'                                │
│ 5 bytes │ sql_state_marker + sql_state       │
│ N bytes │ error_message                      │
└─────────┴────────────────────────────────────┘
```

**Result Set** (para SELECT):

```
┌─────────────────────────────────┐
│ Column count      (varint)      │
├─────────────────────────────────┤
│ Column Definition 1             │
│ Column Definition 2             │
│ ...                             │
├─────────────────────────────────┤
│ EOF packet (si protocolo viejo) │
├─────────────────────────────────┤
│ Row 1                           │
│ Row 2                           │
│ ...                             │
├─────────────────────────────────┤
│ OK/EOF packet (fin de filas)    │
└─────────────────────────────────┘
```

**Column Definition**:

```
┌─────────┬──────────────────────────┐
│ string  │ catalog ("def")          │
│ string  │ schema (db name)         │
│ string  │ table                    │
│ string  │ org_table                │
│ string  │ name                     │
│ string  │ org_name                 │
│ 1 byte  │ 0x0c (filler)            │
│ 2 bytes │ character_set            │
│ 4 bytes │ column_length            │
│ 1 byte  │ column_type              │
│ 2 bytes │ flags                    │
│ 1 byte  │ decimals                 │
│ 2 bytes │ filler (0x0000)          │
└─────────┴──────────────────────────┘
```

**Text Row** (cada fila en resultado textual):

Cada columna se envía como:

```
┌─────────────────────────────────┐
│ Si NULL:  0xfb                  │
│ Si no:    length + value        │
│   length: varint (1-9 bytes)    │
│   value:  N bytes en texto      │
└─────────────────────────────────┘
```

### 3.6 Varint (Length-Encoded Integer)

MySQL usa enteros de longitud variable:

```
Rango              │ Representación
───────────────────────────────────────
0-251              │ 1 byte directo
252-65535          │ 0xfc + 2 bytes little-endian
65536-16777215     │ 0xfd + 3 bytes little-endian
16777216-...       │ 0xfe + 8 bytes little-endian
```

### 3.7 Length-Encoded String

```
┌────────┬──────────────────────────┐
│ varint │ length                   │
│ N      │ bytes del string (UTF-8) │
└────────┴──────────────────────────┘
```

---

## 4. Fase 2: Implementación Paso a Paso

### 4.1 Estructura del Proyecto

```
mysql_driver/
├── __init__.py           # exports públicos
├── connection.py         # clase Connection (PEP 249)
├── cursor.py             # clase Cursor (PEP 249)
├── protocol/
│   ├── __init__.py
│   ├── packet.py         # lectura/escritura de paquetes MySQL
│   ├── handshake.py      # parseo del handshake inicial
│   ├── auth.py           # autenticación (caching_sha2_password, mysql_native_password)
│   ├── types.py          # constantes: tipo de columna, flags, comandos
│   └── charset.py        # mapeo charset_id → encoding Python
├── exceptions.py         # Error, DatabaseError, IntegrityError, etc.
└── constants.py          # capability flags, command IDs, etc.
```

### 4.2 Capa de Paquetes — `protocol/packet.py`

```python
import struct

class MySQLPacket:
    """Representa un paquete MySQL (header 4 bytes + payload)."""

    HEADER_FORMAT = "<I"  # 3 bytes length + 1 byte seq (empaquetado como int little-endian)

    @staticmethod
    def read_from_socket(sock, bufsize=4096):
        """Lee un paquete completo del socket."""
        # 1. Leer header (4 bytes)
        header = _read_exactly(sock, 4)
        payload_length = header[0] | (header[1] << 8) | (header[2] << 16)
        sequence_id = header[3]

        # 2. Leer payload
        payload = _read_exactly(sock, payload_length)

        # 3. Manejar paquetes múltiples (>16MB)
        #    (por simplicidad, omitimos este caso aquí)

        return sequence_id, payload

    @staticmethod
    def write_to_socket(sock, sequence_id, payload):
        """Escribe un paquete en el socket."""
        length = len(payload)
        header = struct.pack("<I", length)[:3] + bytes([sequence_id & 0xff])
        sock.sendall(header + payload)


def _read_exactly(sock, n):
    """Lee exactamente n bytes del socket."""
    data = bytearray()
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError("Conexión cerrada por el servidor")
        data.extend(chunk)
    return bytes(data)
```

### 4.3 Handshake — `protocol/handshake.py`

```python
from src.protocol.packet import MySQLPacket
from src.constants import Capability

class Handshake:
    """Parsea el HandshakeV10 del servidor."""

    def __init__(self, payload):
        self.protocol_version = payload[0]
        pos = 1

        # Server version (null-terminated)
        end = payload.index(0, pos)
        self.server_version = payload[pos:end].decode("utf-8")
        pos = end + 1

        # Connection ID (4 bytes)
        self.connection_id = struct.unpack_from("<I", payload, pos)[0]
        pos += 4

        # Auth plugin data part 1 (8 bytes)
        self.auth_plugin_data_part1 = payload[pos:pos+8]
        pos += 8

        # Filler (1 byte, debe ser 0x00)
        pos += 1  # skip filler

        # Capability flags lower 2 bytes
        self.capability_flags_lower = struct.unpack_from("<H", payload, pos)[0]
        pos += 2

        # Character set (1 byte)
        self.character_set = payload[pos]
        pos += 1

        # Status flags (2 bytes)
        self.status_flags = struct.unpack_from("<H", payload, pos)[0]
        pos += 2

        # Capability flags upper 2 bytes
        self.capability_flags_upper = struct.unpack_from("<H", payload, pos)[0]
        pos += 2

        # Calcular capability flags completas
        self.capability_flags = self.capability_flags_lower | (self.capability_flags_upper << 16)

        # Length of auth plugin data (1 byte, o salt length)
        if pos < len(payload):
            auth_plugin_data_len = payload[pos]
            pos += 1
        else:
            auth_plugin_data_len = 0

        # Reserved (10 bytes, salt si el server es viejo)
        pos += 10 if (self.capability_flags & Capability.SECURE_CONNECTION) else 0

        # Auth plugin data part 2 (al menos 12 bytes, hasta auth_plugin_data_len - 8)
        if self.capability_flags & Capability.SECURE_CONNECTION:
            end = pos + max(12, auth_plugin_data_len - 8)
            self.auth_plugin_data_part2 = payload[pos:end]
        else:
            self.auth_plugin_data_part2 = b""

        # Auth plugin name (si el flag está activo)
        if self.capability_flags & Capability.PLUGIN_AUTH:
            end = payload.index(0, pos)
            self.auth_plugin_name = payload[pos:end].decode("utf-8")
        else:
            self.auth_plugin_name = "mysql_native_password"

    @property
    def scramble(self):
        """Scramble completo (auth_plugin_data)."""
        return self.auth_plugin_data_part1 + self.auth_plugin_data_part2
```

### 4.4 Autenticación — `protocol/auth.py`

#### 4.4.1 `mysql_native_password` (MySQL 5.x)

```python
import hashlib

def mysql_native_password(password, scramble):
    """Calcula el hash para mysql_native_password."""
    if not password:
        return b""

    # SHA1(password)
    hash1 = hashlib.sha1(password.encode("utf-8")).digest()

    # SHA1(SHA1(password))
    hash2 = hashlib.sha1(hash1).digest()

    # SHA1(scramble + hash2)
    hash3 = hashlib.sha1(scramble + hash2).digest()

    # XOR: hash1 XOR hash3
    return bytes(a ^ b for a, b in zip(hash1, hash3))
```

#### 4.4.2 `caching_sha2_password` (MySQL 8.x, default)

```python
def caching_sha2_password(password, scramble, public_key=None):
    """Calcula el hash para caching_sha2_password."""
    if not password:
        return b""

    password_bytes = password.encode("utf-8")

    # SHA256(password) XOR SHA256(scramble + SHA256(SHA256(password)))
    sha256_pass = hashlib.sha256(password_bytes).digest()
    sha256_sha256_pass = hashlib.sha256(sha256_pass).digest()
    hash_xor = hashlib.sha256(scramble + sha256_sha256_pass).digest()

    return bytes(a ^ b for a, b in zip(sha256_pass, hash_xor))


def caching_sha2_full_handshake(sock, password, scramble, sequence_id):
    """Intercambio completo para caching_sha2_password (con RSA)."""
    # Fase 1: enviar XOR hash
    auth_response = caching_sha2_password(password, scramble)
    # ... (enviar en paquete de login)

    # Fase 2: servidor puede responder con:
    #   0x01 + 3 bytes → fast auth (éxito)
    #   0x01 + 4 bytes → requiere intercambio RSA

    # Si requiere RSA:
    #   1. Servidor envía clave pública (o se obtiene de archivo)
    #   2. Cliente cifra password + '\0' con RSA-OAEP
    #   3. Envía cifrado al servidor
```

### 4.5 Connection — `connection.py`

```python
import socket
from src.protocol.packet import MySQLPacket
from src.protocol.handshake import Handshake
from src.protocol.auth import mysql_native_password, caching_sha2_password
from src.cursor import Cursor
from src.constants import Command, Capability
from src.exceptions import OperationalError, ProgrammingError


class Connection:
    def __init__(self, host="localhost", port=3306, user="root",
                 password="", database=None, charset="utf8mb4"):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.charset = charset
        self._sock = None
        self._sequence_id = 0
        self._server_capabilities = 0

    def connect(self):
        """Abre conexión TCP y realiza handshake + auth."""
        # 1. Conexión TCP
        self._sock = socket.create_connection((self.host, self.port))
        self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        # 2. Recibir handshake del servidor
        seq, payload = MySQLPacket.read_from_socket(self._sock)
        handshake = Handshake(payload)

        # 3. Construir respuesta de autenticación
        client_caps = (
            Capability.LONG_PASSWORD |
            Capability.PROTOCOL_41 |
            Capability.SECURE_CONNECTION |
            Capability.PLUGIN_AUTH |
            Capability.PLUGIN_AUTH_LENENC_CLIENT_DATA |
            Capability.CONNECT_WITH_DB
        )

        # Elegir plugin de auth
        if handshake.auth_plugin_name == "caching_sha2_password":
            auth_response = caching_sha2_password(
                self.password, handshake.scramble
            )
        else:
            auth_response = mysql_native_password(
                self.password, handshake.scramble
            )

        # 4. Construir payload de login
        payload = bytearray()
        # client capabilities (4 bytes)
        payload += struct.pack("<I", client_caps)
        # max packet size (4 bytes)
        payload += struct.pack("<I", 16777215)
        # charset (1 byte) — utf8mb4_general_ci = 45
        charset_id = 45
        payload.append(charset_id)
        # reserved (23 bytes de ceros)
        payload += b"\x00" * 23
        # username (null-terminated)
        payload += self.user.encode("utf-8") + b"\x00"
        # auth response (length-encoded)
        payload += bytes([len(auth_response)]) + auth_response
        # database (null-terminated, si aplica)
        if self.database:
            payload += self.database.encode("utf-8") + b"\x00"
        # auth plugin name (null-terminated)
        payload += handshake.auth_plugin_name.encode("utf-8") + b"\x00"

        # 5. Enviar login
        MySQLPacket.write_to_socket(self._sock, 1, bytes(payload))

        # 6. Leer respuesta
        seq, resp = MySQLPacket.read_from_socket(self._sock)
        if resp[0] == 0xff:
            error_code = struct.unpack_from("<H", resp, 1)[0]
            error_msg = resp[4:].decode("utf-8")
            raise OperationalError(f"{error_code}: {error_msg}")

        self._sequence_id = seq

    def cursor(self):
        return Cursor(self)

    def _send_command(self, command, arg=b""):
        """Envía un comando al servidor."""
        payload = bytes([command]) + arg
        MySQLPacket.write_to_socket(self._sock, self._sequence_id, payload)
        self._sequence_id = (self._sequence_id + 1) & 0xff

    def close(self):
        if self._sock:
            self._send_command(Command.QUIT)
            self._sock.close()
            self._sock = None
```

### 4.6 Cursor — `cursor.py`

```python
from src.protocol.packet import MySQLPacket
from src.protocol.types import ColumnType
from src.constants import Command
from src.exceptions import ProgrammingError
import struct


class Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.description = None
        self._rows = []
        self._rowcount = -1
        self._arraysize = 1

    def execute(self, query, params=None):
        """Ejecuta una consulta SQL con parámetros opcionales."""
        if params:
            query = self._escape_params(query, params)

        # Enviar COM_QUERY
        self.connection._send_command(Command.QUERY, query.encode("utf-8"))

        # Leer respuesta
        seq, payload = MySQLPacket.read_from_socket(
            self.connection._sock
        )
        self.connection._sequence_id = seq

        first_byte = payload[0]

        if first_byte == 0xff:
            # Error
            error_code = struct.unpack_from("<H", payload, 1)[0]
            error_msg = payload[4:].decode("utf-8")
            raise ProgrammingError(f"{error_code}: {error_msg}")

        elif first_byte == 0x00:
            # OK packet (INSERT/UPDATE/DELETE sin filas)
            ok = self._parse_ok_packet(payload)
            self._rowcount = ok["affected_rows"]
            self.description = None
            self._rows = []

        else:
            # Result set (SELECT)
            column_count = self._read_varint(payload, 0)
            self._rows = []
            self.description = []

            # Leer definiciones de columnas
            for i in range(column_count):
                seq, col_payload = MySQLPacket.read_from_socket(
                    self.connection._sock
                )
                self.connection._sequence_id = seq
                col_def = self._parse_column_definition(col_payload)
                self.description.append(col_def)

            # Leer EOF (protocolo ≤ 4.0) o OK (protocolo ≥ 4.1)
            # En la práctica: leer hasta que el primer byte sea 0xfe o 0x00

            # Leer filas
            while True:
                seq, row_payload = MySQLPacket.read_from_socket(
                    self.connection._sock
                )
                self.connection._sequence_id = seq

                if row_payload[0] in (0xfe, 0x00):
                    break  # EOF o OK = fin de filas

                row = self._parse_text_row(row_payload, column_count)
                self._rows.append(row)

            self._rowcount = len(self._rows)

        return self._rowcount

    def fetchone(self):
        if not self._rows:
            return None
        return self._rows.pop(0)

    def fetchall(self):
        result = self._rows[:]
        self._rows = []
        return result

    def _parse_ok_packet(self, payload):
        """Parsea un OK packet."""
        pos = 1
        affected_rows, pos = self._read_varint(payload, pos)
        last_insert_id, pos = self._read_varint(payload, pos)
        status_flags = struct.unpack_from("<H", payload, pos)[0]
        pos += 2
        warnings = struct.unpack_from("<H", payload, pos)[0]
        pos += 2
        return {
            "affected_rows": affected_rows,
            "last_insert_id": last_insert_id,
            "status_flags": status_flags,
            "warnings": warnings,
        }

    def _parse_column_definition(self, payload):
        """Parsea una definición de columna."""
        pos = 0
        catalog, pos = self._read_lenenc_string(payload, pos)
        schema, pos = self._read_lenenc_string(payload, pos)
        table, pos = self._read_lenenc_string(payload, pos)
        org_table, pos = self._read_lenenc_string(payload, pos)
        name, pos = self._read_lenenc_string(payload, pos)
        org_name, pos = self._read_lenenc_string(payload, pos)

        pos += 1  # filler (0x0c)

        charset = struct.unpack_from("<H", payload, pos)[0]
        pos += 2
        column_length = struct.unpack_from("<I", payload, pos)[0]
        pos += 4
        column_type = payload[pos]
        pos += 1
        flags = struct.unpack_from("<H", payload, pos)[0]
        pos += 2
        decimals = payload[pos]
        pos += 1

        return {
            "name": name.decode("utf-8") if isinstance(name, bytes) else name,
            "type": column_type,
            "charset": charset,
            "length": column_length,
            "flags": flags,
            "decimals": decimals,
        }

    def _parse_text_row(self, payload, column_count):
        """Parsea una fila en formato de texto."""
        row = []
        pos = 0
        for _ in range(column_count):
            if pos >= len(payload):
                break
            if payload[pos] == 0xfb:
                row.append(None)
                pos += 1
            else:
                length, pos = self._read_varint(payload, pos)
                value = payload[pos:pos+length].decode("utf-8")
                pos += length
                row.append(value)
        return row

    # --- Utilidades de parsing ---

    def _read_varint(self, data, pos):
        """Lee un length-encoded integer de MySQL."""
        first = data[pos]
        if first < 0xfc:
            return first, pos + 1
        elif first == 0xfc:
            return struct.unpack_from("<H", data, pos + 1)[0], pos + 3
        elif first == 0xfd:
            return struct.unpack_from("<I", data, pos + 1)[0] & 0xffffff, pos + 4
        elif first == 0xfe:
            return struct.unpack_from("<Q", data, pos + 1)[0], pos + 9

    def _read_lenenc_string(self, data, pos):
        """Lee un length-encoded string."""
        length, pos = self._read_varint(data, pos)
        value = data[pos:pos+length]
        return value, pos + length

    def _escape_params(self, query, params):
        """Reemplaza %s por valores escapados."""
        # Implementación básica (debe escaparse contra SQL injection)
        escaped = []
        for p in params:
            if p is None:
                escaped.append("NULL")
            elif isinstance(p, int):
                escaped.append(str(p))
            elif isinstance(p, str):
                escaped.append(f"'{p.replace(chr(39), chr(92) + chr(39))}'")
            else:
                escaped.append(str(p))
        return query % tuple(escaped)
```

### 4.7 Constantes — `constants.py`

```python
class Command:
    SLEEP = 0x00
    QUIT = 0x01
    INIT_DB = 0x02
    QUERY = 0x03
    FIELD_LIST = 0x04
    CREATE_DB = 0x05
    DROP_DB = 0x06
    REFRESH = 0x07
    SHUTDOWN = 0x08
    STATISTICS = 0x09
    PROCESS_INFO = 0x0a
    CONNECT = 0x0b
    PROCESS_KILL = 0x0c
    DEBUG = 0x0d
    PING = 0x0e
    TIME = 0x0f
    DELAYED_INSERT = 0x10
    CHANGE_USER = 0x11
    BINLOG_DUMP = 0x12
    TABLE_DUMP = 0x13
    CONNECT_OUT = 0x14
    STMT_PREPARE = 0x16
    STMT_EXECUTE = 0x17
    STMT_SEND_LONG_DATA = 0x18
    STMT_CLOSE = 0x19
    STMT_RESET = 0x1a
    SET_OPTION = 0x1b
    STMT_FETCH = 0x1c


class Capability:
    LONG_PASSWORD = 1
    FOUND_ROWS = 1 << 1
    LONG_FLAG = 1 << 2
    CONNECT_WITH_DB = 1 << 3
    NO_SCHEMA = 1 << 4
    COMPRESS = 1 << 5
    ODBC = 1 << 6
    LOCAL_FILES = 1 << 7
    IGNORE_SPACE = 1 << 8
    PROTOCOL_41 = 1 << 9
    INTERACTIVE = 1 << 10
    SSL = 1 << 11
    IGNORE_SIGPIPE = 1 << 12
    TRANSACTIONS = 1 << 13
    RESERVED = 1 << 14
    SECURE_CONNECTION = 1 << 15
    MULTI_STATEMENTS = 1 << 16
    MULTI_RESULTS = 1 << 17
    PS_MULTI_RESULTS = 1 << 18
    PLUGIN_AUTH = 1 << 19
    CONNECT_ATTRS = 1 << 20
    PLUGIN_AUTH_LENENC_CLIENT_DATA = 1 << 21
    CAN_HANDLE_EXPIRED_PASSWORDS = 1 << 22
    SESSION_TRACK = 1 << 23
    DEPRECATE_EOF = 1 << 24
```

### 4.8 Excepciones — `exceptions.py`

```python
class Error(Exception):
    """Base para todas las excepciones del driver."""

class DatabaseError(Error):
    """Error relacionado con la base de datos."""

class DataError(DatabaseError):
    """Error en datos (división por cero, valor fuera de rango, etc.)."""

class OperationalError(DatabaseError):
    """Error operacional (conexión perdida, timeout, etc.)."""

class IntegrityError(DatabaseError):
    """Error de integridad (FK, unique constraint, etc.)."""

class InternalError(DatabaseError):
    """Error interno del motor."""

class ProgrammingError(DatabaseError):
    """Error de programación (tabla no existe, SQL mal formado, etc.)."""

class NotSupportedError(DatabaseError):
    """Operación no soportada."""
```

### 4.9 Tipos de Columna — `protocol/types.py`

```python
class ColumnType:
    DECIMAL = 0x00
    TINY = 0x01
    SHORT = 0x02
    LONG = 0x03
    FLOAT = 0x04
    DOUBLE = 0x05
    NULL = 0x06
    TIMESTAMP = 0x07
    LONGLONG = 0x08
    INT24 = 0x09
    DATE = 0x0a
    TIME = 0x0b
    DATETIME = 0x0c
    YEAR = 0x0d
    NEWDATE = 0x0e
    VARCHAR = 0x0f
    BIT = 0x10
    TIMESTAMP2 = 0x11
    DATETIME2 = 0x12
    TIME2 = 0x13
    TYPED_ARRAY = 0x14
    JSON = 0xf5
    NEWDECIMAL = 0xf6
    ENUM = 0xf7
    SET = 0xf8
    TINY_BLOB = 0xf9
    MEDIUM_BLOB = 0xfa
    LONG_BLOB = 0xfb
    BLOB = 0xfc
    VAR_STRING = 0xfd
    STRING = 0xfe
    GEOMETRY = 0xff
```

### 4.10 `__init__.py` — API Pública

```python
from .connection import Connection
from .cursor import Cursor
from .exceptions import (
    Error, DatabaseError, DataError,
    OperationalError, IntegrityError,
    InternalError, ProgrammingError, NotSupportedError,
)

def connect(host="localhost", port=3306, user="root",
            password="", database=None, charset="utf8mb4"):
    """Crea y retorna una conexión MySQL."""
    conn = Connection(
        host=host, port=port, user=user,
        password=password, database=database,
        charset=charset,
    )
    conn.connect()
    return conn


__all__ = [
    "connect", "Connection", "Cursor",
    "Error", "DatabaseError", "DataError",
    "OperationalError", "IntegrityError",
    "InternalError", "ProgrammingError", "NotSupportedError",
]
```

### 4.11 Uso Final

```python
from mysql_driver import connect

conn = connect(
    host="localhost",
    port=3306,
    user="root",
    password="secret",
    database="test",
)

cursor = conn.cursor()

# SELECT
cursor.execute("SELECT * FROM users WHERE age > %s", [18])
for row in cursor.fetchall():
    print(row)

# INSERT
cursor.execute("INSERT INTO users (name, age) VALUES (%s, %s)", ["Alice", 30])
print(f"Filas afectadas: {cursor.rowcount}")
print(f"ID insertado: {cursor.lastrowid}")

conn.close()
```

---

## 5. Fases de Desarrollo Recomendadas

```
FASE 1 ─── Protocolo básico
  ├── Conexión TCP al puerto 3306
  ├── Lectura/escritura de paquetes MySQL
  ├── Parseo del HandshakeV10
  └── Autenticación mysql_native_password

FASE 2 ─── Consultas
  ├── COM_QUERY con SELECT
  ├── Parseo de columnas (ColumnDefinition)
  ├── Parseo de filas (TextRow)
  ├── COM_QUERY con INSERT/UPDATE/DELETE
  └── Parseo de OK/ERR packets

FASE 3 ─── API PEP 249
  ├── Connection.connect()
  ├── Connection.cursor()
  ├── Connection.commit() / rollback()
  ├── Cursor.execute() con parámetros %s
  ├── Cursor.fetchone() / fetchall()
  ├── Cursor.description
  └── Manejo de excepciones estándar

FASE 4 ─── Autenticación moderna
  ├── caching_sha2_password (MySQL 8+)
  ├── Intercambio RSA para full auth
  ├── mysql_clear_password
  └── Soporte SSL/TLS

FASE 5 ─── Prepared Statements
  ├── COM_STMT_PREPARE
  ├── COM_STMT_EXECUTE (bind de parámetros binarios)
  ├── COM_STMT_CLOSE
  └── COM_STMT_FETCH

FASE 6 ─── Optimizaciones
  ├── Bufferización de lectura/escritura
  ├── Compresión de paquetes (zlib)
  ├── Multi-statement y multi-resultset
  ├── Conexiones asíncronas (asyncio)
  ├── Connection pooling
  └── Type casting automático (bytes → int/float/datetime)
```

---

## 6. Referencias

| Recurso | URL |
|---|---|
| Documentación oficial del protocolo MySQL | `dev.mysql.com/doc/dev/mysql-server/latest/PAGE_PROTOCOL.html` |
| PEP 249 — Python DB-API 2.0 | `peps.python.org/pep-0249/` |
| Código fuente de PyMySQL (referencia) | `github.com/PyMySQL/PyMySQL` |
| Código fuente de mysql-connector-python | `github.com/mysql/mysql-connector-python` |
| MariaDB Knowledge Base (protocolo) | `mariadb.com/kb/en/library/protocol/` |
| Wireshark (para depurar paquetes) | `wireshark.org` |

---

## 7. Consejos Prácticos

1. **Usa Wireshark** para capturar tráfico entre un driver existente (PyMySQL) y MySQL. Así ves los bytes exactos que se intercambian.

2. **Prueba contra MySQL en Docker**:

```bash
docker run --name mysql-test -e MYSQL_ROOT_PASSWORD=secret -p 3306:3306 -d mysql:8.0
```

3. **Implementa primero el parsing de paquetes** con pruebas unitarias usando hex dumps.

4. **No empieces con SSL**. Primero haz funcionar sin cifrado.

5. **El protocolo MySQL tiene modos**: texto (COM_QUERY) y binario (COM_STMT_EXECUTE). Empieza con texto.

6. **El ORM de este proyecto (`src/orm/db/mysql.py`)** usa `pymysql` como driver subyacente. Si creas tu propio driver, puedes reemplazar `pymysql` con tu implementación para tener un stack 100% propio.

---

*Documento generado como guía conceptual para implementar un driver MySQL desde cero en Python.*

Mejor buscó una vida o me mato por que estar leyendo demasiado es aburrido y tendría que leer
demás y ya me aburri de leer.
Ademas si hagaramos ejemplos de PyMySQL o del propio repositorio de github del mariadb-connector-c
https://github.com/mariadb-corporation/mariadb-connector-c
podremos ver que hay más constantes que deberiamos de definir así como también configuraciones que
se deben de realizar por lo que es mejor usar las librerias ya definidas o tomarse el tiempo de crearse
la propia consejo propio se feliz haciendo lo que quieras jajaja.

Pero si es para aprender y hay tiempo lo mejor es aprender de como planear y realizar los proyectos pequeños
para aprender sobre socket, binary, nodos entre otras cosas así que para que rayos escribo esto no sé
lo que si sé es que tengo pereza en seguir leyendo como se comienza a crear los driver y da pereza también estar
leyendo los repositorios en github de como funcionan dichos proyectos. Pero hay que aprender algo que es lo
bueno y a la vez lo malo así que suerte.

Lo bueno es que ya tengo un plan para crear un driver de mysql este plan esta basado en el repositorio de
PyMySQL https://github.com/PyMySQL/PyMySQL, asi que mirenlo y jodete quién está escribiendo este comienza
a escribir código