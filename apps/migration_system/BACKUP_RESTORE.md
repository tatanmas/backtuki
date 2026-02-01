# Sistema de Backup/Restore desde GCP

Sistema enterprise modularizado para restaurar Tuki desde backups de Google Cloud Platform.

## Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│                    FRONTEND (React)                          │
│  Panel de Migración → Pestaña "Restore desde Backup"        │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                  API ENDPOINTS (Django)                      │
│  POST /api/v1/migration/upload-backup/                      │
│  POST /api/v1/migration/restore-backup/<id>/                │
│  GET  /api/v1/migration/restore-status/<id>/                │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              RESTORE SERVICE (Orquestador)                   │
│  - Extrae tar.gz                                             │
│  - Valida estructura                                         │
│  - Coordina SQL + Media restore                              │
└─────────┬────────────────────────────┬──────────────────────┘
          │                            │
          ▼                            ▼
┌──────────────────────┐    ┌──────────────────────┐
│  SQL RESTORE SERVICE │    │ MEDIA RESTORE SERVICE│
│  - Stop Django       │    │  - Extrae archivos   │
│  - Drop/Create DB    │    │  - Sync a volume     │
│  - pg_restore        │    │  - Verifica          │
│  - Restart Django    │    └──────────────────────┘
└──────────────────────┘
```

## Servicios Modulares

Todos los servicios son <150 líneas, siguiendo principios SOLID:

### 1. BackupValidator (~80 líneas)
**Ubicación**: `apps/migration_system/services/backup_restore/validator.py`

**Responsabilidad**: Validar estructura del backup .tar.gz

```python
validator = BackupValidator()
result = validator.validate(backup_path)
# result = {
#     'valid': bool,
#     'errors': [],
#     'warnings': [],
#     'metadata': {'sql_dumps_count': 1, 'media_files_count': 567}
# }
```

### 2. SQLRestoreService (~120 líneas)
**Ubicación**: `apps/migration_system/services/backup_restore/sql_restore.py`

**Responsabilidad**: Restaurar PostgreSQL desde dump

```python
sql_service = SQLRestoreService(job)
result = sql_service.restore(sql_dump_path)
# result = {
#     'success': bool,
#     'records_restored': int,
#     'errors': [],
#     'safety_backup': '/tmp/backup.sql.gz'
# }
```

**Proceso**:
1. Crea backup de seguridad de DB actual
2. Detiene servicios Django (backend, celery)
3. Drop y recreate database
4. Ejecuta `pg_restore` desde dump
5. Verifica integridad (cuenta registros)
6. Reinicia servicios

### 3. MediaRestoreService (~100 líneas)
**Ubicación**: `apps/migration_system/services/backup_restore/media_restore.py`

**Responsabilidad**: Sincronizar archivos media al volume Docker

```python
media_service = MediaRestoreService(job)
result = media_service.restore(media_source_dir)
# result = {
#     'success': bool,
#     'files_copied': int,
#     'total_size_mb': float,
#     'errors': []
# }
```

**Proceso**:
1. Cuenta archivos y tamaño
2. Usa contenedor Alpine temporal para copiar al volume
3. Verifica sincronización

### 4. RestoreService (~140 líneas)
**Ubicación**: `apps/migration_system/services/backup_restore/restore_service.py`

**Responsabilidad**: Orquestador principal

```python
restore_service = RestoreService(job)
result = restore_service.execute()
# result = {
#     'success': bool,
#     'summary': {
#         'sql_records': 1234,
#         'media_files': 567,
#         'media_size_mb': 123.45
#     },
#     'errors': []
# }
```

## API Endpoints

### 1. Upload Backup
```http
POST /api/v1/migration/upload-backup/
Content-Type: multipart/form-data
Authorization: Bearer <token> (SuperUser only)

Body:
- backup_file: archivo .tar.gz
- restore_sql: true (opcional)
- restore_media: true (opcional)

Response 201:
{
  "success": true,
  "job": {
    "id": "uuid",
    "status": "uploaded",
    "file_size_mb": 123.45,
    "original_filename": "backup-20260201.tar.gz"
  }
}
```

### 2. Execute Restore
```http
POST /api/v1/migration/restore-backup/<job_id>/
Content-Type: application/json
Authorization: Bearer <token> (SuperUser only)

Body:
{
  "confirm": true  // REQUIRED
}

Response 200:
{
  "success": true,
  "job_id": "uuid",
  "status": "restoring",
  "message": "Restore iniciado. Monitorea el progreso..."
}
```

### 3. Check Status
```http
GET /api/v1/migration/restore-status/<job_id>/
Authorization: Bearer <token>

Response 200:
{
  "id": "uuid",
  "status": "restoring",
  "progress_percent": 45,
  "current_step": "Restaurando SQL...",
  "sql_records_restored": 1234,
  "media_files_restored": 567,
  "started_at": "2026-02-01T15:30:00Z"
}
```

### 4. List Backup Jobs
```http
GET /api/v1/migration/backup-jobs/?status=completed&limit=10
Authorization: Bearer <token>

Response 200:
{
  "jobs": [...],
  "total": 10
}
```

## Modelo de Datos

### BackupJob
```python
class BackupJob(TimeStampedModel):
    id = UUIDField(primary_key=True)
    backup_file = FileField(upload_to='backups/%Y/%m/')
    file_size_mb = DecimalField(max_digits=10, decimal_places=2)
    original_filename = CharField(max_length=255)
    
    # Estado
    status = CharField(max_length=20)  # uploaded, validating, restoring, completed, failed
    progress_percent = IntegerField(default=0)
    current_step = CharField(max_length=255)
    
    # Opciones
    restore_sql = BooleanField(default=True)
    restore_media = BooleanField(default=True)
    create_backup_before = BooleanField(default=True)
    
    # Resultados
    sql_records_restored = IntegerField(default=0)
    media_files_restored = IntegerField(default=0)
    media_size_mb = DecimalField(max_digits=10, decimal_places=2)
    
    # Metadata
    backup_metadata = JSONField(default=dict)
    safety_backup_path = CharField(max_length=500)
    
    # Auditoría
    uploaded_by = ForeignKey(User)
    started_at = DateTimeField(null=True)
    completed_at = DateTimeField(null=True)
    duration_seconds = IntegerField(null=True)
    error_message = TextField(blank=True)
```

## Flujo Completo de Uso

### Paso 1: Generar Backup en GCP
```bash
cd /Users/sebamasretamal/Desktop/cursor/tukifull/backup
./02_backup_before_destroy.sh tukiprod us-central1
```

Output: `backups-20260201-HHMMSS/`

### Paso 2: Comprimir Backup
```bash
BACKUP_DIR=$(ls -d backups-* | tail -n 1)
tar -czf backup-gcp-$(date +%Y%m%d).tar.gz "$BACKUP_DIR"
```

### Paso 3: Subir via API
```bash
curl -X POST http://tukitickets.duckdns.org:8000/api/v1/migration/upload-backup/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "backup_file=@backup-gcp-20260201.tar.gz" \
  -F "restore_sql=true" \
  -F "restore_media=true"
```

O desde el **Panel Web** (recomendado):
1. Ir a `/admin/migration/` o panel de migración
2. Pestaña "Restore desde Backup"
3. Seleccionar archivo .tar.gz
4. Click "Subir Backup"

### Paso 4: Ejecutar Restore
```bash
curl -X POST http://tukitickets.duckdns.org:8000/api/v1/migration/restore-backup/<JOB_ID>/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"confirm": true}'
```

O desde el **Panel Web**:
1. Ver lista de backups subidos
2. Click en "Restaurar"
3. Confirmar en modal de advertencia
4. Monitorear progreso en tiempo real

### Paso 5: Monitorear Progreso
```bash
curl http://tukitickets.duckdns.org:8000/api/v1/migration/restore-status/<JOB_ID>/ \
  -H "Authorization: Bearer YOUR_TOKEN"
```

O en el **Panel Web**: barra de progreso actualizada cada 2 segundos.

## Manejo de Conflictos (Merge de Admins)

El sistema hace **MERGE** de usuarios:

1. **Preserva admin de Dako**: El superuser que ejecuta el restore NO se borra
2. **Restaura usuarios del backup**: Todos los usuarios del backup GCP se importan
3. **Conflictos por email**: Si un usuario del backup tiene el mismo email que uno en Dako:
   - Se actualiza el usuario de Dako con los datos del backup
   - Se preserva el `is_superuser=True` si ya lo tenía en Dako

**Ejemplo**:
```
Dako antes del restore:
- admin@tuki.cl (superuser, password: DakoPass123)

Backup GCP contiene:
- admin@tuki.cl (superuser, password: GCPPass456)
- user1@tuki.cl (staff)
- user2@tuki.cl (normal)

Resultado después del restore:
- admin@tuki.cl (superuser, password: GCPPass456) ← Actualizado con datos de GCP
- user1@tuki.cl (staff) ← Importado de GCP
- user2@tuki.cl (normal) ← Importado de GCP
```

## Seguridad

### Permisos
- **Solo SuperUsers** pueden subir y ejecutar restores
- Requiere confirmación explícita (`confirm: true`)
- Tokens de migración con permisos `admin`

### Safety Backup
Antes de restaurar SQL, se crea automáticamente un backup de la DB actual en:
```
/tmp/tuki_safety_backup_<timestamp>.sql.gz
```

Para rollback manual si algo falla:
```bash
docker exec -i backtuki-db-1 pg_restore \
  -U tuki_user -d tuki_production \
  --no-owner --no-acl \
  < /tmp/tuki_safety_backup_*.sql.gz
```

### Logs
Todos los pasos se loggean en:
- Django logs: `/app/logs/`
- Job progress: campo `current_step` en BackupJob
- Errores: campo `error_message` y `error_traceback`

## Troubleshooting

### Error: "Backup inválido"
**Causa**: Estructura del tar.gz no es la esperada

**Solución**: Verificar que el backup tenga:
```
backups-*/
├── cloudsql/
│   └── tuki-db-prod-tuki_production-*.sql.gz
└── gcs/
    └── tuki-media-prod-*/
```

### Error: "No se pudo detener servicios Django"
**Causa**: docker-compose no está en el PATH o no hay permisos

**Solución**: Ejecutar manualmente:
```bash
docker-compose stop backtuki-backend-1 backtuki-celery-worker-1 backtuki-celery-beat-1
```

### Error: "pg_restore failed"
**Causa**: Dump SQL incompatible o corrupto

**Solución**: 
1. Verificar integridad del .sql.gz: `gzip -t archivo.sql.gz`
2. Revisar versión de PostgreSQL (debe ser compatible)
3. Usar safety backup para rollback

### Restore se quedó en "restoring" sin avanzar
**Causa**: Proceso colgado o error no capturado

**Solución**:
1. Ver logs: `docker logs backtuki-backend-1`
2. Reiniciar servicios: `docker-compose restart`
3. Marcar job como failed manualmente en Django Admin

## Performance

### Tiempos Estimados
- Backup pequeño (<100MB): ~2-5 minutos
- Backup mediano (100MB-1GB): ~10-20 minutos
- Backup grande (>1GB): ~30-60 minutos

### Optimizaciones
- Restore SQL usa `--no-owner --no-acl` para velocidad
- Media sync usa contenedor Alpine (ligero)
- Progreso se actualiza cada 5-10% para reducir writes a DB

## Roadmap

### Futuras Mejoras
- [ ] Ejecutar restore en Celery task (async)
- [ ] WebSocket para progreso en tiempo real
- [ ] Compresión adicional de backups (zstd)
- [ ] Restore selectivo (solo ciertos modelos)
- [ ] Scheduling de backups automáticos
- [ ] Integración con S3/GCS para storage de backups

## Soporte

Para issues o preguntas:
- Email: tecnologia@tuki.cl
- Logs: `docker logs backtuki-backend-1`
- Django Admin: http://tukitickets.duckdns.org:8000/admin/
