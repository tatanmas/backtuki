# 🚀 Despliegue en Google Cloud Platform (GCP) - Guía Empresarial

## 📁 Migración del Sistema de Almacenamiento

### Situación Actual
- **Almacenamiento Local**: `/app/media/event_images/`
- **Problema**: Las imágenes se pierden al reiniciar contenedores
- **Limitación**: No escalable para múltiples instancias

### Solución GCP
- **Google Cloud Storage**: Almacenamiento persistente y escalable
- **CDN Integration**: Distribución global para mejor performance
- **Backup Automático**: Versionado y recuperación de archivos

## 🔧 Configuración Requerida

### 1. Servicios GCP Necesarios

```bash
# Habilitar servicios en GCP
gcloud services enable storage-api.googleapis.com
gcloud services enable sql-admin.googleapis.com
gcloud services enable redis.googleapis.com
gcloud services enable run.googleapis.com
```

### 2. Crear Service Account

```bash
# Crear service account
gcloud iam service-accounts create tuki-storage-sa \
    --display-name="Tuki Storage Service Account"

# Asignar permisos
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member="serviceAccount:tuki-storage-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/storage.admin"

# Crear clave
gcloud iam service-accounts keys create ./service-account-key.json \
    --iam-account=tuki-storage-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com
```

### 3. Crear Cloud Storage Bucket

```bash
# Crear bucket para media files
gsutil mb gs://tuki-media-bucket

# Configurar permisos públicos para imágenes
gsutil iam ch allUsers:objectViewer gs://tuki-media-bucket

# Configurar lifecycle para optimización de costos
gsutil lifecycle set lifecycle.json gs://tuki-media-bucket
```

## 📋 Variables de Entorno para Producción

```bash
# Django Settings
SECRET_KEY=your-super-secret-key
DEBUG=False
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com

# Google Cloud Storage
USE_GCP=true
GS_PROJECT_ID=your-gcp-project-id
GS_BUCKET_NAME=tuki-media-bucket
GS_CREDENTIALS=/path/to/service-account-key.json

# Database (Cloud SQL)
DB_ENGINE=django.db.backends.postgresql
DB_NAME=tuki_production
DB_USER=tuki_user
DB_PASSWORD=your-secure-password
DB_HOST=your-cloud-sql-connection-name

# Redis (Cloud Memorystore)
REDIS_URL=redis://your-redis-ip:6379/0
```

## 🔄 Migración de Imágenes Existentes

### Script de Migración

```python
# migrate_images_to_gcp.py
import os
from django.core.management.base import BaseCommand
from google.cloud import storage
from apps.events.models import EventImage

class Command(BaseCommand):
    def handle(self, *args, **options):
        client = storage.Client()
        bucket = client.bucket('tuki-media-bucket')
        
        for event_image in EventImage.objects.all():
            local_path = event_image.image.path
            if os.path.exists(local_path):
                blob_name = f"media/{event_image.image.name}"
                blob = bucket.blob(blob_name)
                
                blob.upload_from_filename(local_path)
                self.stdout.write(f"Migrated: {event_image.image.name}")
```

### Ejecutar Migración

```bash
# Desde el contenedor
docker-compose exec web python manage.py migrate_images_to_gcp

# O crear un job de migración una sola vez
```

## 🚀 Cambios en el Código

### 1. Backend (Ya implementado)
- ✅ `google-cloud-storage` agregado a requirements.txt
- ✅ Configuración GCP en `production.py`
- ✅ Variables de entorno configuradas

### 2. URLs de Imágenes
```python
# Antes (local)
MEDIA_URL = 'media/'

# Después (GCP)
MEDIA_URL = 'https://storage.googleapis.com/tuki-media-bucket/media/'
# O con CDN personalizado
MEDIA_URL = 'https://cdn.yourdomain.com/media/'
```

### 3. Upload de Imágenes
- ✅ No requiere cambios en el frontend
- ✅ django-storages maneja automáticamente GCS
- ✅ URLs se generan automáticamente

## 📊 Beneficios Post-Migración

### Performance
- **CDN Global**: Imágenes distribuidas mundialmente
- **Cache Headers**: Cache de 24h configurado
- **Compression**: Optimización automática

### Escalabilidad
- **Multi-instancia**: Múltiples contenedores pueden acceder
- **Auto-scaling**: Se adapta al tráfico
- **Backup**: Versionado automático

### Costos
- **Pay-per-use**: Solo pagas por lo que usas
- **Lifecycle policies**: Archivos antiguos a storage más barato
- **Compression**: Reducción de ancho de banda

## 🔧 Comandos de Despliegue

### Cloud Run Deployment
```bash
# Build y deploy
gcloud run deploy tuki-backend \
    --image gcr.io/YOUR_PROJECT/tuki-backend \
    --platform managed \
    --region us-central1 \
    --allow-unauthenticated \
    --set-env-vars USE_GCP=true,GS_PROJECT_ID=YOUR_PROJECT

# Configurar dominio personalizado
gcloud run domain-mappings create \
    --service tuki-backend \
    --domain api.yourdomain.com
```

## ⚠️ Consideraciones Importantes

1. **Backup Existente**: Hacer backup de `/app/media/` antes de migrar
2. **Testing**: Probar upload en staging antes de producción  
3. **DNS**: Configurar dominios antes del go-live
4. **SSL**: Cloud Run incluye SSL automático
5. **Monitoreo**: Configurar logging y alertas

## 📈 Próximos Pasos

1. **Crear buckets de GCP**
2. **Configurar service accounts**
3. **Deploy a staging**
4. **Migrar imágenes existentes**
5. **Deploy a producción**
6. **Configurar CDN (opcional)**

Este setup te dará un sistema nivel Ticketmaster, completamente escalable y listo para producción enterprise. 🎫✨ 