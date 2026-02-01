# 🚀 Sistema de Migración Enterprise - Tuki Platform

Sistema robusto y enterprise-grade para migrar toda la plataforma Tuki entre entornos (GCP ↔ Servidor Local) mediante comunicación directa entre backends.

## Características

- ✅ **Backend-a-Backend**: Comunicación directa sin scripts SSH externos
- ✅ **Bidireccional**: GCP ↔ Local con el mismo código
- ✅ **Verificación de Integridad**: Checksums, counts, relaciones
- ✅ **Rollback Automático**: Si falla, revierte cambios
- ✅ **Progress Tracking**: Monitoreo en tiempo real
- ✅ **Seguridad Enterprise**: Tokens específicos, rate limiting, auditoría
- ✅ **Mobile-First UI**: Interfaz responsive en React
- ✅ **Modularizado**: Servicios separados, fácil de mantener

## Inicio Rápido

### 1. Migrar GCP → Servidor Local

**En el servidor local, ejecuta:**

```bash
# Opción A: Usando management command
python manage.py pull_from_source \
  --source-url https://prop.cl \
  --source-token TOKEN_GCP \
  --verify

# Opción B: Usando la interfaz web
# Ve a /superadmin/migration/ y usa el tab "Pull"
```

### 2. Migrar Servidor Local → GCP

**En el servidor local, ejecuta:**

```bash
# Opción A: Usando management command
python manage.py push_to_target \
  --target-url https://prop.cl \
  --target-token TOKEN_GCP \
  --verify

# Opción B: Usando la interfaz web
# Ve a /superadmin/migration/ y usa el tab "Push"
```

### 3. Crear Token de Migración

**Antes de migrar, crea un token en el backend origen:**

```bash
python manage.py create_migration_token \
  --description "Migración GCP a Local" \
  --permissions read_write \
  --expires-in 24h
```

Guarda el token generado y úsalo en los comandos de migración.

## Componentes del Sistema

### Backend (Django)

#### Modelos

- **MigrationJob**: Trackea estado y progreso de migraciones
- **MigrationLog**: Logs detallados de operaciones
- **MigrationCheckpoint**: Puntos de restauración para rollback
- **MigrationToken**: Tokens de autenticación específicos

#### Servicios

- **PlatformExportService**: Exporta todos los datos
- **PlatformImportService**: Importa datos con rollback
- **FileTransferService**: Transfiere archivos entre GCS y local
- **IntegrityVerificationService**: Verifica integridad post-migración

#### Management Commands

- `export_platform`: Export a archivo
- `import_platform`: Import desde archivo
- `push_to_target`: Push a backend destino
- `pull_from_source`: Pull desde backend origen
- `create_migration_token`: Genera tokens

#### API Endpoints

- `POST /api/v1/migration/export/`: Inicia export
- `GET /api/v1/migration/export-status/{job_id}/`: Estado del export
- `GET /api/v1/migration/download-export/{job_id}/`: Descarga export
- `POST /api/v1/migration/receive-import/`: Recibe datos para importar
- `POST /api/v1/migration/receive-file/`: Recibe archivo individual
- `GET /api/v1/migration/media-list/`: Lista archivos media
- `GET /api/v1/migration/download-file/`: Descarga archivo
- `POST /api/v1/migration/verify/`: Verifica integridad
- `POST /api/v1/migration/rollback/{job_id}/`: Rollback
- `GET /api/v1/migration/jobs/`: Lista jobs
- `GET /api/v1/migration/jobs/{job_id}/logs/`: Logs de job

### Frontend (React)

#### Componentes

- **MigrationPage**: Página principal con tabs
- **ExportPanel**: Panel de exportación
- **ImportPanel**: Panel de importación con drag & drop
- **PushPullPanel**: Panel para push/pull backend-a-backend
- **MigrationJobCard**: Card para mostrar estado de jobs

#### API Client

- `migrationApi`: Cliente TypeScript para todos los endpoints

## Casos de Uso

### Caso 1: Migración Completa GCP → Local

**Escenario**: Necesitas migrar toda la plataforma de GCP a tu servidor local.

**Pasos**:

1. **En GCP**: Crear token de migración
   ```bash
   python manage.py create_migration_token \
     --description "Migración a local" \
     --permissions read \
     --expires-in 24h
   ```

2. **En Local**: Pull desde GCP
   ```bash
   python manage.py pull_from_source \
     --source-url https://prop.cl \
     --source-token TOKEN_AQUI \
     --verify \
     --create-checkpoint
   ```

3. **Verificar**: Accede a tu servidor local y verifica que todo funciona

4. **Actualizar DNS**: Apunta tu dominio al servidor local

5. **Apagar GCP**: Reduce min-instances a 0 para ahorrar costos

**Tiempo estimado**: 30-60 minutos

### Caso 2: Backup y Restore

**Escenario**: Quieres hacer un backup antes de cambios importantes.

**Pasos**:

1. **Crear export**:
   ```bash
   python manage.py export_platform \
     --output /backups/tuki-backup-$(date +%Y%m%d).json.gz \
     --include-media \
     --compress
   ```

2. **Si algo sale mal, restaurar**:
   ```bash
   python manage.py import_platform \
     --input /backups/tuki-backup-20260120.json.gz \
     --verify \
     --overwrite
   ```

### Caso 3: Sincronización Incremental

**Escenario**: Solo quieres migrar cambios recientes.

**Pasos**:

1. **Export incremental** (solo cambios desde fecha):
   ```bash
   python manage.py export_platform \
     --output /tmp/incremental.json.gz \
     --since 2026-01-15
   ```

2. **Import con merge**:
   ```bash
   python manage.py import_platform \
     --input /tmp/incremental.json.gz \
     --merge \
     --verify
   ```

### Caso 4: Clonación de Ambiente

**Escenario**: Quieres clonar producción a staging.

**Pasos**:

1. **En Producción**: Export
2. **En Staging**: Import con overwrite
3. **Sanitizar datos sensibles** (opcional)

## Configuración

### Settings (config/settings/base.py)

```python
MIGRATION_SYSTEM = {
    'EXPORT_DIR': BASE_DIR / 'exports',
    'CHECKPOINT_DIR': BASE_DIR / 'checkpoints',
    'MAX_EXPORT_SIZE_GB': 10,
    'CHUNK_SIZE': 1000,
    'FILE_CHUNK_SIZE_MB': 10,
    'PARALLEL_TRANSFERS': 5,
    'TOKEN_EXPIRY_HOURS': 24,
    'ALLOWED_SOURCE_DOMAINS': [
        'prop.cl',
        'tuki.cl',
        'tukitickets.duckdns.org',
        'localhost',
    ],
    'VERIFY_SSL': True,
}
```

### Agregar a INSTALLED_APPS

```python
INSTALLED_APPS = [
    # ...
    'apps.migration_system',
]
```

### Agregar rutas de API

```python
# api/v1/urls.py
urlpatterns = [
    # ...
    path('migration/', include('api.v1.migration.urls')),
]
```

## Seguridad

### Tokens de Migración

Los tokens de migración son específicos para operaciones de migración y tienen:

- **Expiración**: 24 horas por defecto
- **Permisos granulares**: read, write, read_write, admin
- **IP whitelisting**: Opcional
- **Dominio whitelisting**: Opcional
- **Un solo uso**: Opcional
- **Auditoría**: Tracking completo de uso

### Best Practices

1. **Nunca reutilices tokens de API normales** para migración
2. **Tokens de corta duración**: 24 horas máximo
3. **Revoca tokens** después de usar
4. **Usa HTTPS** siempre en producción
5. **Whitelist IPs/dominios** cuando sea posible
6. **Monitorea logs** de auditoría regularmente

## Troubleshooting

### Error: "Token inválido o expirado"

**Causa**: El token expiró o fue revocado.

**Solución**: Crea un nuevo token con `create_migration_token`.

### Error: "Formato de export inválido"

**Causa**: El archivo export está corrupto o es de una versión incompatible.

**Solución**: Genera un nuevo export desde el origen.

### Error: "Verificación de integridad falló"

**Causa**: Algunos datos no se importaron correctamente.

**Solución**: 
1. Revisa los logs para ver qué falló
2. Si hay checkpoint, ejecuta rollback
3. Reintenta el import con `--overwrite`

### Error: "Checksum mismatch"

**Causa**: Un archivo se corrompió durante la transferencia.

**Solución**: Reintenta la transferencia. El sistema tiene retry automático.

## Monitoreo

### Ver Jobs Activos

```bash
# Listar últimos 20 jobs
python manage.py shell
>>> from apps.migration_system.models import MigrationJob
>>> jobs = MigrationJob.objects.all()[:20]
>>> for job in jobs:
...     print(f"{job.id}: {job.direction} - {job.status} ({job.progress_percent}%)")
```

### Ver Logs de un Job

```bash
python manage.py shell
>>> from apps.migration_system.models import MigrationJob
>>> job = MigrationJob.objects.get(id='uuid-aqui')
>>> for log in job.logs.all():
...     print(f"[{log.level}] {log.message}")
```

### Verificar Checkpoints

```bash
python manage.py shell
>>> from apps.migration_system.models import MigrationCheckpoint
>>> checkpoints = MigrationCheckpoint.objects.filter(is_valid=True)
>>> for cp in checkpoints:
...     print(f"{cp.name}: {cp.total_records} registros, {cp.snapshot_size_mb} MB")
```

## Performance

### Optimizaciones Implementadas

- **Bulk operations**: Usa `bulk_create` para inserts masivos
- **Chunked processing**: Procesa datos en chunks de 1000 registros
- **Parallel transfers**: Transfiere hasta 5 archivos en paralelo
- **Streaming**: Descarga archivos grandes en chunks
- **Compression**: gzip reduce tamaño en ~70%

### Tiempos Estimados

| Operación | Pequeño (<1GB) | Mediano (1-5GB) | Grande (>5GB) |
|-----------|----------------|-----------------|---------------|
| Export | 2-5 min | 5-15 min | 15-30 min |
| Import | 3-7 min | 7-20 min | 20-45 min |
| Push/Pull | 5-10 min | 10-30 min | 30-60 min |

## Arquitectura

### Flujo de Datos: Pull from Source

```
1. Admin ejecuta: python manage.py pull_from_source
2. Local → GCP: POST /api/v1/migration/export/
3. GCP exporta datos (chunked)
4. Local ← GCP: GET /api/v1/migration/download-export/
5. Local valida integridad del export
6. Local crea checkpoint
7. Local importa datos en orden de dependencias
8. Local ← GCP: GET /api/v1/migration/download-file/ (para cada archivo)
9. Local verifica integridad final
10. Local marca job como completado
```

### Orden de Dependencias

Los modelos se exportan/importan en este orden para respetar ForeignKeys:

1. User
2. Organizer
3. Location, EventCategory
4. Event
5. TicketTier, TicketCategory
6. Order
7. OrderItem
8. Ticket
9. EventImage
10. Forms y FormResponses
11. Etc.

## Roadmap

### v1.1 (Próxima versión)

- [ ] Ejecución asíncrona con Celery
- [ ] WebSocket para progress en tiempo real
- [ ] Sincronización incremental automática
- [ ] Compresión selectiva por modelo
- [ ] Encriptación de exports sensibles

### v2.0 (Futuro)

- [ ] Replicación en tiempo real
- [ ] Multi-tenant support
- [ ] Migración selectiva por organizer
- [ ] Dashboard de analytics de migraciones

## Soporte

Para problemas o preguntas:

1. Revisa los logs en `/api/v1/migration/jobs/{job_id}/logs/`
2. Verifica checkpoints disponibles
3. Consulta esta documentación
4. Revisa `EXAMPLES.md` para casos de uso específicos

---

**Versión**: 1.0.0  
**Última actualización**: 2026-01-20  
**Autor**: Tuki Platform Team
