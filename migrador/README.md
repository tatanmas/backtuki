# 🚀 MIGRADOR GCP → HOME SERVER

Esta carpeta contiene todos los scripts y configuración necesarios para migrar Tuki desde GCP a tu servidor local.

## 📁 Archivos

### Scripts Principales

| Archivo | Descripción |
|---------|-------------|
| `clone-from-gcp.sh` | ⭐ **SCRIPT PRINCIPAL** - Clona todo desde GCP al servidor local |
| `setup-gcloud-on-server.sh` | Configura gcloud CLI en el servidor (ejecutar primero) |
| `deploy-to-homeserver.sh` | Despliega infraestructura (usado por clone-from-gcp.sh) |
| `migrate-db-from-gcp.sh` | Migra solo la base de datos |
| `sync-media-from-gcp.sh` | Sincroniza solo archivos media |

### Configuración

| Archivo | Descripción |
|---------|-------------|
| `docker-compose.homeserver.yml` | Docker Compose para servidor local |

## 🚀 Inicio Rápido

### Paso 1: Configurar gcloud CLI en el servidor

```bash
cd /Users/sebamasretamal/Desktop/cursor/tukifull/backtuki/migrador
./setup-gcloud-on-server.sh
```

### Paso 2: Clonar todo desde GCP

```bash
./clone-from-gcp.sh
```

**Eso es todo.** El script hace:
1. ✅ Detiene tatanfoto_backend (libera puerto 8000)
2. ✅ Crea estructura en `/home/tatan/Escritorio/tuki-platform`
3. ✅ Clona base de datos desde Cloud SQL
4. ✅ Clona archivos media desde GCS
5. ✅ Transfiere código desde tu Mac
6. ✅ Levanta servicios Docker
7. ✅ Restaura base de datos
8. ✅ Ejecuta migraciones Django

**Tiempo estimado:** 30-60 minutos

## 📋 Requisitos

- ✅ Acceso SSH al servidor (tukitickets.duckdns.org:2222)
- ✅ gcloud CLI instalado en el servidor (el script lo instala)
- ✅ Credenciales GCP configuradas en el servidor
- ✅ Docker y Docker Compose en el servidor (ya los tienes)

## 🔍 Verificación

Después de ejecutar, verifica:

```bash
ssh -p 2222 tatan@tukitickets.duckdns.org
cd /home/tatan/Escritorio/tuki-platform
docker-compose ps
```

Deberías ver todos los servicios corriendo.

Acceder a:
- Backend: http://tukitickets.duckdns.org:8000
- Admin: http://tukitickets.duckdns.org:8000/admin/

Credenciales:
- Usuario: `admin`
- Password: `TukiAdmin2025!`

## 🆘 Troubleshooting

### Error: gcloud no está instalado
Ejecuta primero: `./setup-gcloud-on-server.sh`

### Error: No se puede conectar a Cloud SQL
Verifica credenciales: `gcloud auth list`

### Error: Puerto 8000 ocupado
El script detiene tatanfoto automáticamente, pero si falla:
```bash
ssh -p 2222 tatan@tukitickets.duckdns.org
docker stop tatanfoto_backend
docker rm tatanfoto_backend
```

### Ver logs
```bash
ssh -p 2222 tatan@tukitickets.duckdns.org
cd /home/tatan/Escritorio/tuki-platform
docker-compose logs -f
```

## 📚 Documentación Completa

Ver:
- `../PLAN_MIGRACION_HOMESERVER.md` - Plan detallado
- `../RESUMEN_MIGRACION_HOMESERVER.md` - Resumen ejecutivo

