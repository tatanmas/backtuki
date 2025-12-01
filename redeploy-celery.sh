#!/bin/bash

# 🚀 CELERY FORCE REDEPLOY - Tuki Platform
# Forza un redeploy completo de Celery con código fresco
# Elimina imágenes viejas y construye desde cero

set -e

# Configuration
PROJECT_ID="tukiprod"
REGION="us-central1"
# Usar el mismo tag que el backend para alinearlos
IMAGE_TAG="v7-production"
WORKER_SERVICE_NAME="tuki-celery-worker"
BEAT_SERVICE_NAME="tuki-celery-beat"
WORKER_IMAGE="us-central1-docker.pkg.dev/${PROJECT_ID}/tuki-repo/tuki-celery-worker:${IMAGE_TAG}"
BEAT_IMAGE="us-central1-docker.pkg.dev/${PROJECT_ID}/tuki-repo/tuki-celery-beat:${IMAGE_TAG}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_step() {
    echo -e "${BLUE}🔧 $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

echo "🚀 TUKI CELERY - FORCE REDEPLOY"
echo "====================================="
echo "Tag: ${IMAGE_TAG}"
echo "Esto construirá imágenes frescas SIN cache y redeployará todo"
echo ""

# Step 1: Build Celery images WITH --no-cache
print_step "PASO 1: Building Celery images SIN CACHE (código fresco)..."

# Crear un cloudbuild temporal con --no-cache
cat > /tmp/cloudbuild-celery-force.yaml << EOF
steps:
  # Build Celery Worker Image (SIN CACHE)
  - name: 'gcr.io/cloud-builders/docker'
    args: [
      'build',
      '--no-cache',
      '--pull',
      '-f', 'Dockerfile.celery-worker',
      '-t', 'us-central1-docker.pkg.dev/tukiprod/tuki-repo/tuki-celery-worker:${IMAGE_TAG}',
      '-t', 'us-central1-docker.pkg.dev/tukiprod/tuki-repo/tuki-celery-worker:latest',
      '.'
    ]
    id: 'build-celery-worker'

  # Build Celery Beat Image (SIN CACHE)
  - name: 'gcr.io/cloud-builders/docker'
    args: [
      'build',
      '--no-cache',
      '--pull',
      '-f', 'Dockerfile.celery-beat',
      '-t', 'us-central1-docker.pkg.dev/tukiprod/tuki-repo/tuki-celery-beat:${IMAGE_TAG}',
      '-t', 'us-central1-docker.pkg.dev/tukiprod/tuki-repo/tuki-celery-beat:latest',
      '.'
    ]
    id: 'build-celery-beat'

  # Push Celery Worker Image
  - name: 'gcr.io/cloud-builders/docker'
    args: [
      'push',
      'us-central1-docker.pkg.dev/tukiprod/tuki-repo/tuki-celery-worker:${IMAGE_TAG}'
    ]
    waitFor: ['build-celery-worker']

  # Push Celery Beat Image
  - name: 'gcr.io/cloud-builders/docker'
    args: [
      'push',
      'us-central1-docker.pkg.dev/tukiprod/tuki-repo/tuki-celery-beat:${IMAGE_TAG}'
    ]
    waitFor: ['build-celery-beat']

  # Push Latest Tags
  - name: 'gcr.io/cloud-builders/docker'
    args: [
      'push',
      'us-central1-docker.pkg.dev/tukiprod/tuki-repo/tuki-celery-worker:latest'
    ]
    waitFor: ['build-celery-worker']

  - name: 'gcr.io/cloud-builders/docker'
    args: [
      'push',
      'us-central1-docker.pkg.dev/tukiprod/tuki-repo/tuki-celery-beat:latest'
    ]
    waitFor: ['build-celery-beat']

options:
  machineType: 'E2_HIGHCPU_8'
  logging: CLOUD_LOGGING_ONLY

timeout: 1200s
EOF

cd /Users/sebamasretamal/Desktop/cursor/tukifull/backtuki
gcloud builds submit --config /tmp/cloudbuild-celery-force.yaml

if [ $? -eq 0 ]; then
    print_success "Celery images construidas SIN CACHE y pusheadas exitosamente!"
else
    print_error "Failed to build Celery images"
    rm /tmp/cloudbuild-celery-force.yaml
    exit 1
fi

rm /tmp/cloudbuild-celery-force.yaml

# Step 2: Limpiar revisiones viejas del Worker
print_step "PASO 2: Limpiando revisiones viejas del Celery Worker..."
OLD_REVISIONS=$(gcloud run revisions list --service=${WORKER_SERVICE_NAME} --region=${REGION} --format="value(name)" 2>/dev/null | tail -n +2 || echo "")
if [ ! -z "$OLD_REVISIONS" ]; then
    for revision in $OLD_REVISIONS; do
        if [ ! -z "$revision" ]; then
            print_step "  Eliminando revisión: $revision"
            gcloud run revisions delete $revision --region=${REGION} --quiet 2>/dev/null || true
        fi
    done
    print_success "Revisiones viejas eliminadas"
else
    print_warning "No hay revisiones viejas para eliminar"
fi

# Step 3: Deploy Celery Worker
print_step "PASO 3: Deploying Celery Worker (FORZADO)..."

# 🚀 ENTERPRISE: Deploy with Dockerfile CMD (no command override)
# This ensures we use the CMD from Dockerfile: ["python", "/app/celery_health_server.py"]
# Reset any previously set command to use Dockerfile default
gcloud run deploy ${WORKER_SERVICE_NAME} \
  --image ${WORKER_IMAGE} \
  --region ${REGION} \
  --platform managed \
  --no-allow-unauthenticated \
  --port 8080 \
  --min-instances 1 \
  --max-instances 20 \
  --concurrency 1 \
  --memory 8Gi \
  --cpu 4 \
  --timeout 3600 \
  --env-vars-file cloud-run-env.yaml \
  --vpc-connector serverless-conn \
  --vpc-egress private-ranges-only \
  --service-account 187635794409-compute@developer.gserviceaccount.com \
  --command="" \
  --args=""

if [ $? -eq 0 ]; then
    print_success "Celery Worker deployed successfully!"
else
    print_error "Failed to deploy Celery Worker"
    exit 1
fi

# Step 4: Limpiar revisiones viejas del Beat
print_step "PASO 4: Limpiando revisiones viejas del Celery Beat..."
OLD_REVISIONS=$(gcloud run revisions list --service=${BEAT_SERVICE_NAME} --region=${REGION} --format="value(name)" 2>/dev/null | tail -n +2 || echo "")
if [ ! -z "$OLD_REVISIONS" ]; then
    for revision in $OLD_REVISIONS; do
        if [ ! -z "$revision" ]; then
            print_step "  Eliminando revisión: $revision"
            gcloud run revisions delete $revision --region=${REGION} --quiet 2>/dev/null || true
        fi
    done
    print_success "Revisiones viejas eliminadas"
else
    print_warning "No hay revisiones viejas para eliminar"
fi

# Step 5: Deploy Celery Beat
print_step "PASO 5: Deploying Celery Beat (FORZADO)..."

# 🚀 ENTERPRISE: Deploy with Dockerfile CMD (no command override)
# This ensures we use the CMD from Dockerfile
# Reset any previously set command to use Dockerfile default
gcloud run deploy ${BEAT_SERVICE_NAME} \
  --image ${BEAT_IMAGE} \
  --region ${REGION} \
  --platform managed \
  --no-allow-unauthenticated \
  --port 8080 \
  --min-instances 1 \
  --max-instances 1 \
  --concurrency 1 \
  --memory 512Mi \
  --cpu 1 \
  --timeout 3600 \
  --env-vars-file cloud-run-env.yaml \
  --vpc-connector serverless-conn \
  --vpc-egress private-ranges-only \
  --service-account 187635794409-compute@developer.gserviceaccount.com \
  --command="" \
  --args=""

if [ $? -eq 0 ]; then
    print_success "Celery Beat deployed successfully!"
else
    print_error "Failed to deploy Celery Beat"
    exit 1
fi

# Step 6: Wait for services to stabilize
print_step "PASO 6: Waiting for Celery services to stabilize..."
sleep 30

# Get service URLs for reference
WORKER_URL=$(gcloud run services describe ${WORKER_SERVICE_NAME} --region=${REGION} --format="value(status.url)" 2>/dev/null || echo "N/A")
BEAT_URL=$(gcloud run services describe ${BEAT_SERVICE_NAME} --region=${REGION} --format="value(status.url)" 2>/dev/null || echo "N/A")

print_success "Celery services redeployed y estabilizando!"
echo ""
echo "====================================="
print_success "🎉 CELERY FORCE REDEPLOY COMPLETADO!"
echo ""
echo "📋 RESUMEN:"
echo "============================"
echo "🔧 Worker URL: ${WORKER_URL}"
echo "📅 Beat URL: ${BEAT_URL}"
echo "🏷️  Tag usado: ${IMAGE_TAG}"
echo ""
echo "📋 PRÓXIMOS PASOS:"
echo "=============="
echo "1. ✅ Celery Worker redeployed con código fresco"
echo "2. ✅ Celery Beat redeployed con código fresco"
echo "3. 🧪 Testear envío de emails creando una orden de prueba"
echo "4. 🔍 Monitorear logs: gcloud run services logs read ${WORKER_SERVICE_NAME} --region=${REGION}"
echo ""
print_success "Celery está ahora ejecutando el código más reciente! 📧"

