# 🏠 TUKI HOME SERVER DEPLOYMENT

## 🎯 Inicio Rápido

### Ejecutar Migración Completa Automatizada

```bash
cd /Users/sebamasretamal/Desktop/cursor/tukifull/backtuki
./full-migration-gcp-to-homeserver.sh
```

Este script ejecutará automáticamente:
1. ✅ Despliegue de infraestructura
2. ✅ Migración de base de datos
3. ✅ Sincronización de archivos media

**Tiempo estimado:** 30-60 minutos

---

## 📁 Archivos Creados

### Scripts de Migración

| Script | Descripción |
|--------|-------------|
| `full-migration-gcp-to-homeserver.sh` | **SCRIPT MAESTRO** - Ejecuta todo el proceso |
| `deploy-to-homeserver.sh` | Despliega infraestructura en servidor local |
| `migrate-db-from-gcp.sh` | Migra base de datos desde Cloud SQL |
| `sync-media-from-gcp.sh` | Sincroniza archivos desde GCS |

### Archivos de Configuración

| Archivo | Descripción |
|---------|-------------|
| `docker-compose.homeserver.yml` | Docker Compose para servidor local |
| `config/settings/homeserver.py` | Django settings para servidor local |

---

## 🔧 Configuración

### Servidor Local
- **Host:** tukitickets.duckdns.org
- **Puerto SSH:** 2222
- **Usuario:** tatan

### Puertos Asignados (sin conflictos con servicios existentes)
- **Backend:** 8001 (TatanFoto usa 8000)
- **PostgreSQL:** 5435 (AuroraDev usa 5434)
- **Redis:** 6380 (Immich usa 6379)

---

## 📊 URLs de Acceso

Después de la migración:

| Servicio | URL |
|----------|-----|
| Backend | http://tukitickets.duckdns.org:8001 |
| Admin Panel | http://tukitickets.duckdns.org:8001/admin/ |
| API | http://tukitickets.duckdns.org:8001/api/v1/ |
| Health Check | http://tukitickets.duckdns.org:8001/healthz |

### Credenciales Admin

- **Usuario:** admin
- **Email:** admin@tuki.cl
- **Password:** TukiAdmin2025!

---

## 🛠️ Comandos Útiles

### Ver logs

```bash
ssh -p 2222 tatan@tukitickets.duckdns.org
cd /home/tatan/tuki-platform

# Logs del backend
docker-compose logs -f tuki-backend

# Logs de Celery
docker-compose logs -f tuki-celery-worker

# Todos los logs
docker-compose logs -f
```

### Gestión de servicios

```bash
# Ver estado
docker-compose ps

# Reiniciar servicios
docker-compose restart

# Reiniciar solo backend
docker-compose restart tuki-backend

# Detener todo
docker-compose down

# Levantar todo
docker-compose up -d
```

### Base de datos

```bash
# Acceder a PostgreSQL
docker-compose exec tuki-db psql -U tuki_user -d tuki_production

# Backup manual
docker-compose exec tuki-db pg_dump -U tuki_user -Fc tuki_production > backup.dump

# Restore manual
docker-compose exec -T tuki-db pg_restore -U tuki_user -d tuki_production < backup.dump
```

---

## 🔄 Migración Inversa (Home Server → GCP)

Si necesitas volver a GCP:

```bash
# 1. Crear backup de base de datos local
ssh -p 2222 tatan@tukitickets.duckdns.org
cd /home/tatan/tuki-platform
docker-compose exec tuki-db pg_dump -U tuki_user -Fc tuki_production > /tmp/backup.dump

# 2. Descargar backup
scp -P 2222 tatan@tukitickets.duckdns.org:/tmp/backup.dump ./

# 3. Subir a GCS
gsutil cp backup.dump gs://tuki-backups/restore-from-homeserver.dump

# 4. Importar a Cloud SQL
gcloud sql import sql tuki-db-prod \
  gs://tuki-backups/restore-from-homeserver.dump \
  --database=tuki_production

# 5. Sincronizar media
ssh -p 2222 tatan@tukitickets.duckdns.org "cd /home/tatan/tuki-platform && tar -czf /tmp/media.tar.gz media/"
scp -P 2222 tatan@tukitickets.duckdns.org:/tmp/media.tar.gz ./
tar -xzf media.tar.gz
gsutil -m rsync -r media/ gs://tuki-media-prod-1759240560/

# 6. Reactivar servicios GCP
gcloud run services update tuki-backend --min-instances=1 --region=us-central1
gcloud run services update tuki-celery-unified --min-instances=1 --region=us-central1
gcloud run services update tuki-celery-beat --min-instances=1 --region=us-central1
```

---

## 💰 Ahorro de Costos

### Antes (GCP 100%)
- Total: $50-62k CLP/mes (~$300 USD/mes)

### Después (Servidor Local)
- Electricidad: $3-5k/mes
- Cloud Storage (backups): $500/mes
- **Total: $3-5.5k CLP/mes (~$18 USD/mes)**

**Ahorro: $45-57k CLP/mes (90-95%)**

---

## 🆘 Soporte

Para problemas o preguntas:

1. **Revisar logs:** `docker-compose logs`
2. **Verificar estado:** `docker-compose ps`
3. **Reiniciar servicios:** `docker-compose restart`
4. **Consultar plan completo:** Ver `PLAN_MIGRACION_HOMESERVER.md`

---

## 📋 Checklist Post-Migración

- [ ] Verificar que todos los servicios están "Up (healthy)"
- [ ] Acceder al admin panel
- [ ] Verificar eventos existentes
- [ ] Verificar órdenes de compra
- [ ] Verificar imágenes se cargan
- [ ] Crear evento de prueba
- [ ] Configurar Cloudflare Tunnel (opcional)
- [ ] Actualizar DNS
- [ ] Apagar servicios GCP (para ahorro)
- [ ] Configurar backups automáticos

---

**Documentación completa:** `PLAN_MIGRACION_HOMESERVER.md`  
**Fecha de creación:** 18 Enero 2026  
**Versión:** 1.0

