# 🔌 Conectar Base de Datos PostgreSQL a pgAdmin

## 📋 Credenciales de la Base de Datos

Según tu configuración de Docker (`docker-compose.local.yml`), las credenciales son:

| Campo | Valor |
|-------|-------|
| **Host/Address** | `localhost` o `127.0.0.1` |
| **Port** | `5432` |
| **Database** | `tuki_local` |
| **Username** | `tuki_user` |
| **Password** | `tuki_password` |

## 🚀 Pasos para Conectar en pgAdmin

### 1. Abrir pgAdmin

Abre pgAdmin en tu navegador (normalmente `http://localhost:5050` o la URL que configuraste).

### 2. Agregar Nuevo Servidor

1. Click derecho en **"Servers"** en el panel izquierdo
2. Selecciona **"Register"** > **"Server..."**

### 3. Configurar la Conexión

#### Pestaña "General"
- **Name**: `Tuki Local` (o el nombre que prefieras)

#### Pestaña "Connection"
- **Host name/address**: `localhost`
- **Port**: `5432`
- **Maintenance database**: `tuki_local`
- **Username**: `tuki_user`
- **Password**: `tuki_password`
- ✅ Marca **"Save password"** si quieres que guarde la contraseña

### 4. Pestaña "Advanced" (Opcional)
- **DB restriction**: Deja vacío o escribe `tuki_local` para limitar a esta base de datos

### 5. Guardar

Click en **"Save"** para guardar la conexión.

## ✅ Verificar Conexión

Si todo está correcto, deberías ver:
- ✅ El servidor aparece en el panel izquierdo
- ✅ Puedes expandir y ver la base de datos `tuki_local`
- ✅ Puedes ver todas las tablas (schemas > public > tables)

## 🔍 Si No Puedes Conectar

### Verificar que el contenedor está corriendo:

```bash
docker ps | grep postgres
```

Deberías ver algo como:
```
backtuki-db-1    postgres:14    Up X days    0.0.0.0:5432->5432/tcp
```

### Verificar que el puerto está expuesto:

```bash
docker port backtuki-db-1
```

Debería mostrar:
```
5432/tcp -> 0.0.0.0:5432
```

### Verificar conexión directa:

```bash
docker exec -it backtuki-db-1 psql -U tuki_user -d tuki_local
```

Si puedes conectarte, deberías ver el prompt de PostgreSQL.

## 📝 Resumen Rápido

```
Host: localhost
Port: 5432
Database: tuki_local
Username: tuki_user
Password: tuki_password
```

## 🐳 Si Estás Usando Docker Compose Diferente

Si estás usando un archivo `docker-compose.yml` diferente, verifica las credenciales con:

```bash
docker exec backtuki-db-1 env | grep POSTGRES
```

O revisa el archivo `docker-compose.yml` que estés usando.

## 🔐 Cambiar Credenciales (Si es Necesario)

Si necesitas cambiar las credenciales, edita `docker-compose.local.yml`:

```yaml
db:
  image: postgres:14
  environment:
    POSTGRES_DB: tuki_local
    POSTGRES_USER: tuki_user
    POSTGRES_PASSWORD: tu_nueva_password
```

Luego reinicia el contenedor:
```bash
docker-compose -f docker-compose.local.yml down
docker-compose -f docker-compose.local.yml up -d db
```

## 📚 Tablas Importantes para Experiencias

Una vez conectado, las tablas relevantes para experiencias son:

- `organizers_organizer` - Organizadores
- `organizers_organizeruser` - Relación usuarios-organizadores
- `experiences_experience` - Experiencias/Tours
- `experiences_tourlanguage` - Idiomas de tours
- `experiences_tourinstance` - Instancias de tours
- `experiences_tourbooking` - Reservas de tours
- `experiences_organizercredit` - Créditos de organizadores

