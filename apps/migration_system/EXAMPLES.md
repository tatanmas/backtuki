# Ejemplos de Uso - Sistema de Migración

## Ejemplo 1: Migración Completa GCP → Local (Caso Real)

### Contexto
Tienes tu plataforma corriendo en GCP y necesitas migrarla a tu servidor local para ahorrar costos.

### Paso a Paso

#### 1. Preparar Servidor Local

```bash
# Conectar al servidor
ssh -p 2222 tatan@tukitickets.duckdns.org

# Verificar Docker
docker --version
docker-compose --version

# Crear directorio para Tuki
mkdir -p /home/tatan/Escritorio/tuki-platform
cd /home/tatan/Escritorio/tuki-platform
```

#### 2. Clonar Código

```bash
# Desde tu Mac, transferir código
rsync -avz -e "ssh -p 2222" \
  /Users/sebamasretamal/Desktop/cursor/tukifull/backtuki/ \
  tatan@tukitickets.duckdns.org:/home/tatan/Escritorio/tuki-platform/
```

#### 3. Levantar Servicios en Local

```bash
# En el servidor
cd /home/tatan/Escritorio/tuki-platform

# Copiar docker-compose para homeserver
cp docker-compose.homeserver.yml docker-compose.yml

# Levantar servicios
docker-compose up -d

# Verificar que están corriendo
docker-compose ps
```

#### 4. Crear Token en GCP

```bash
# Desde tu Mac, conectar a GCP
gcloud run services proxy tuki-backend --region=us-central1

# En otra terminal
python manage.py create_migration_token \
  --description "Migración a servidor local" \
  --permissions read \
  --expires-in 24h

# Guardar el token que se genera
```

#### 5. Ejecutar Pull desde Local

```bash
# En el servidor local
cd /home/tatan/Escritorio/tuki-platform

# Pull desde GCP
docker-compose exec tuki-backend python manage.py pull_from_source \
  --source-url https://prop.cl \
  --source-token TOKEN_DE_GCP_AQUI \
  --verify \
  --create-checkpoint
```

#### 6. Verificar Migración

```bash
# Ver logs
docker-compose logs tuki-backend | tail -100

# Acceder al admin
# http://tukitickets.duckdns.org:8000/admin/

# Verificar datos
docker-compose exec tuki-backend python manage.py shell
>>> from apps.events.models import Event, Order
>>> print(f"Eventos: {Event.objects.count()}")
>>> print(f"Órdenes: {Order.objects.count()}")
```

#### 7. Actualizar DNS

```bash
# En Cloudflare, cambiar A record de prop.cl
# De: IP de GCP
# A: tukitickets.duckdns.org

# O usar Cloudflare API
curl -X PATCH "https://api.cloudflare.com/client/v4/zones/ZONE_ID/dns_records/RECORD_ID" \
  -H "Authorization: Bearer CLOUDFLARE_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"content":"tukitickets.duckdns.org"}'
```

#### 8. Apagar GCP (Ahorro de Costos)

```bash
# Reducir min-instances a 0
gcloud run services update tuki-backend --min-instances=0 --region=us-central1
gcloud run services update tuki-celery-unified --min-instances=0 --region=us-central1
gcloud run services update tuki-celery-beat --min-instances=0 --region=us-central1

# Verificar que están apagados
gcloud run services list --region=us-central1
```

**Resultado**: Ahorro de ~€10/día (~€300/mes)

---

## Ejemplo 2: Backup Diario Automático

### Contexto
Quieres backups automáticos diarios de tu plataforma.

### Setup

```bash
# Crear script de backup
cat > /home/tatan/scripts/backup-tuki.sh << 'EOF'
#!/bin/bash
DATE=$(date +%Y%m%d)
BACKUP_DIR="/home/tatan/backups"
mkdir -p $BACKUP_DIR

cd /home/tatan/Escritorio/tuki-platform

# Crear backup
docker-compose exec -T tuki-backend python manage.py export_platform \
  --output $BACKUP_DIR/tuki-backup-$DATE.json.gz \
  --include-media \
  --compress

# Subir a GCS (opcional, para redundancia)
gsutil cp $BACKUP_DIR/tuki-backup-$DATE.json.gz gs://tuki-backups/daily/

# Limpiar backups antiguos (más de 7 días)
find $BACKUP_DIR -name "tuki-backup-*.json.gz" -mtime +7 -delete

echo "Backup completado: $DATE"
EOF

chmod +x /home/tatan/scripts/backup-tuki.sh

# Agregar a crontab (diario a las 3 AM)
crontab -e
# Agregar:
0 3 * * * /home/tatan/scripts/backup-tuki.sh >> /home/tatan/backups/backup.log 2>&1
```

---

## Ejemplo 3: Migración Reversa Local → GCP

### Contexto
Tienes un evento grande y necesitas la capacidad de GCP.

### Paso a Paso

#### 1. Crear Token en Local

```bash
# En servidor local
docker-compose exec tuki-backend python manage.py create_migration_token \
  --description "Push a GCP para evento" \
  --permissions write \
  --expires-in 24h
```

#### 2. Reactivar Servicios GCP

```bash
# Desde tu Mac
gcloud run services update tuki-backend --min-instances=1 --region=us-central1
gcloud run services update tuki-celery-unified --min-instances=1 --region=us-central1
gcloud run services update tuki-celery-beat --min-instances=1 --region=us-central1

# Esperar que estén listos (2-3 minutos)
```

#### 3. Push desde Local a GCP

```bash
# En servidor local
docker-compose exec tuki-backend python manage.py push_to_target \
  --target-url https://prop.cl \
  --target-token TOKEN_DE_LOCAL_AQUI \
  --verify
```

#### 4. Actualizar DNS de vuelta a GCP

```bash
# Cambiar A record en Cloudflare
# De: tukitickets.duckdns.org
# A: IP de GCP
```

#### 5. Apagar Local (Opcional)

```bash
# En servidor local
docker-compose down
```

---

## Ejemplo 4: Usar la Interfaz Web

### Acceder a la Interfaz

```
https://prop.cl/superadmin/migration/
```

### Export

1. Ve al tab "Export"
2. Configura opciones (incluir media, comprimir)
3. Click en "Iniciar Export"
4. Espera a que complete
5. Descarga el archivo generado

### Import

1. Ve al tab "Import"
2. Arrastra archivo export o selecciónalo
3. Configura opciones (verificar, checkpoint, overwrite)
4. Click en "Iniciar Import"
5. Monitorea el progreso en tiempo real

### Push

1. Ve al tab "Push"
2. Ingresa URL del destino
3. Ingresa token de autenticación
4. Configura opciones
5. Click en "Iniciar Push"

### Pull

1. Ve al tab "Pull"
2. Ingresa URL del origen
3. Ingresa token de autenticación
4. Configura opciones
5. Click en "Iniciar Pull"

### Ver Historial

1. Ve al tab "Historial"
2. Ve todos los jobs ejecutados
3. Click en "Ver Logs" para detalles
4. Click en "Descargar" para exports completados
5. Click en "Rollback" para revertir imports

---

## Ejemplo 5: Rollback de Migración Fallida

### Contexto
Un import falló y necesitas revertir cambios.

### Pasos

```bash
# Listar jobs recientes
python manage.py shell
>>> from apps.migration_system.models import MigrationJob
>>> jobs = MigrationJob.objects.filter(direction='import').order_by('-created_at')[:5]
>>> for job in jobs:
...     print(f"{job.id}: {job.status} - Checkpoint: {job.checkpoint_id if job.checkpoint else 'N/A'}")

# Ejecutar rollback
>>> from apps.migration_system.services import PlatformImportService
>>> service = PlatformImportService()
>>> result = service.rollback_to_checkpoint('checkpoint-id-aqui')
>>> print(result)
```

**O usando API**:

```bash
curl -X POST https://prop.cl/api/v1/migration/rollback/JOB_ID/ \
  -H "Authorization: MigrationToken TOKEN_AQUI"
```

---

## Ejemplo 6: Migración Solo de Modelos Específicos

### Contexto
Solo quieres migrar eventos, no usuarios ni órdenes.

### Pasos

```bash
# Export solo eventos
python manage.py export_platform \
  --output /tmp/eventos-only.json.gz \
  --models events.Event,events.EventImage,events.TicketTier \
  --compress

# Import en destino
python manage.py import_platform \
  --input /tmp/eventos-only.json.gz \
  --skip-existing \
  --verify
```

---

## Notas Importantes

1. **Downtime**: Durante la migración, la plataforma puede estar no disponible. Planifica en horarios de bajo tráfico.

2. **Backups**: Siempre crea un checkpoint antes de imports importantes.

3. **Verificación**: Siempre usa `--verify` para asegurar integridad.

4. **Tokens**: Revoca tokens después de usar para seguridad.

5. **Logs**: Revisa logs si algo falla. Contienen información detallada.

6. **Testing**: Prueba primero en ambiente de desarrollo antes de producción.
