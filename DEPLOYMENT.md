# 🚀 Tuki Backend - Deployment Guide

## Desarrollo Local

```bash
# Iniciar servicios locales
docker-compose -f docker-compose.local.yml up

# Acceder a:
# Backend: http://localhost:8000
# Admin: http://localhost:8000/admin/
# API Docs: http://localhost:8000/api/docs/
```

## Deployment a Producción

### 1. Deploy Completo (nuevo código)
```bash
./deploy.sh
```

### 2. Solo rebuild (cambios menores)
```bash
gcloud builds submit --config cloudbuild.yaml
gcloud run deploy tuki-backend \
  --image us-central1-docker.pkg.dev/tukiprod/tuki-repo/tuki-backend:v5-fixed \
  --region us-central1
```

## URLs de Producción

- **Backend**: https://tuki-backend-g6mwf7fr6a-uc.a.run.app
- **Dominio**: https://prop.cl
- **Admin**: https://prop.cl/admin/
- **API Docs**: https://prop.cl/api/docs/

## Credenciales Admin

- **Usuario**: admin
- **Email**: admin@tuki.cl  
- **Password**: TukiAdmin2025!

## Arquitectura

```
Frontend (tuki-experiencias) → prop.cl → Cloud Run (tuki-backend) → Cloud SQL
```

## Logs

```bash
# Ver logs del servicio
gcloud run services logs read tuki-backend --region=us-central1

# Ver logs en tiempo real
gcloud run services logs tail tuki-backend --region=us-central1
```

## Archivos Importantes

- `Dockerfile` - Imagen de producción
- `Dockerfile.local` - Desarrollo local
- `entrypoint.sh` - Script de inicio (migraciones + gunicorn)
- `deploy.sh` - Deploy completo automatizado
- `cloud-run-env.yaml` - Variables de entorno de producción
