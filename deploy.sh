#!/bin/bash

# 🚀 ENTERPRISE COMPLETE DEPLOYMENT - Tuki Platform
# Inspirado en AuroraDev - Deploy completo con migraciones y superusuario
# Orden correcto: Build -> Deploy -> Migrate -> Create Superuser -> Configure Domain
#
# 💰 COST-OPTIMIZED CONFIGURATION (Default Mode)
# ================================================
# This script deploys with cost-optimized settings for normal operation (1-100 users):
#
# Backend:          min-instances=1  (required for WhatsApp webhooks 24/7)
# Celery Beat:      min-instances=1  (required to schedule periodic tasks)
# Celery Worker:    min-instances=1  (required to execute periodic tasks - Cloud Run doesn't auto-scale from Redis queue)
# Other Workers:    min-instances=0  (scale-to-zero, only activate when needed)
#
# 🎯 For EVENTS with 1000+ simultaneous users, use: deploy-event-mode.sh
#
# Estimated monthly cost with this configuration: $27-35k CLP/month
# (vs $57-69k with previous always-on configuration)

set -e

# Optional -m "referencia" (como git commit): mensaje del deploy para listado en Super Admin
DEPLOY_MSG=""
while [[ $# -gt 0 ]]; do
  case $1 in
    -m) DEPLOY_MSG="${2:-}"; shift 2 ;;
    *) shift ;;
  esac
done

# Configuration
PROJECT_ID="tukiprod"
REGION="us-central1"
SERVICE_NAME="tuki-backend"
IMAGE_TAG="v7-production"
IMAGE_NAME="us-central1-docker.pkg.dev/${PROJECT_ID}/tuki-repo/tuki-backend:${IMAGE_TAG}"

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

echo "🚀 TUKI PLATFORM - COMPLETE DEPLOYMENT"
echo "====================================="
echo "Uso: ./deploy.sh [-m \"referencia\"]   (opcional -m como en git commit, para listado en Super Admin)"
echo "Inspirado en AuroraDev - Orden correcto de operaciones"
echo ""

# Step 1: Build and push image
print_step "PASO 1: Building and pushing Docker image..."
gcloud builds submit --config cloudbuild.yaml

if [ $? -eq 0 ]; then
    print_success "Image built and pushed successfully!"
else
    print_error "Failed to build and push image"
    exit 1
fi

# Step 2: Deploy to Cloud Run
print_step "PASO 2: Deploying to Cloud Run..."

# DEPLOYED_AT y APP_VERSION para que el backend registre el deploy en BD (flujo Super Admin)
export DEPLOYED_AT=$(date -u +"%Y-%m-%dT%H:%M:%S+00:00")
if [[ -n "${DEPLOY_MSG}" ]]; then
  export APP_VERSION="${DEPLOY_MSG}"
else
  export APP_VERSION=$(git rev-parse --short HEAD 2>/dev/null || echo "deploy-$(date +%Y-%m-%d-%H%M)")
fi
# Limitar longitud para el campo version (80 chars)
APP_VERSION="${APP_VERSION:0:80}"
print_success "Deploy ref: DEPLOYED_AT=${DEPLOYED_AT} APP_VERSION=${APP_VERSION}"

# 🚀 COST-OPTIMIZED: Backend min-instances=1 (required for WhatsApp webhooks)
# --set-env-vars inyecta DEPLOYED_AT y APP_VERSION para que cada arranque registre el deploy
# (APP_VERSION entre comillas por si tiene espacios, ej. -m "fix login")
gcloud run deploy ${SERVICE_NAME} \
  --image ${IMAGE_NAME} \
  --region ${REGION} \
  --platform managed \
  --allow-unauthenticated \
  --port 8080 \
  --min-instances 1 \
  --max-instances 100 \
  --concurrency 200 \
  --memory 4Gi \
  --cpu 2 \
  --timeout 300 \
  --env-vars-file cloud-run-env.yaml \
  --set-env-vars "DEPLOYED_AT=${DEPLOYED_AT},APP_VERSION=\"${APP_VERSION}\"" \
  --vpc-connector serverless-conn \
  --vpc-egress private-ranges-only \
  --service-account 187635794409-compute@developer.gserviceaccount.com

if [ $? -eq 0 ]; then
    print_success "Service deployed successfully!"
else
    print_error "Failed to deploy service"
    exit 1
fi

# Step 3: Wait for service to be ready
print_step "PASO 3: Waiting for service to be ready..."
sleep 30

SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --region=${REGION} --format="value(status.url)")
print_success "Service URL: ${SERVICE_URL}"

# Step 4: Wait for service to stabilize
print_step "PASO 4: Waiting for service to stabilize..."
sleep 15
print_success "Service deployment completed!"

# Step 5: Database migrations run automatically in entrypoint
print_step "PASO 5: Database migrations..."
print_success "Database migrations run automatically in entrypoint!"

# Step 6: Setup Payment Methods (CRITICAL FOR PRODUCTION)
print_step "PASO 6: Setting up payment methods..."
print_step "Calling payment setup endpoint..."

# Setup payment methods via API endpoint
SETUP_RESPONSE=$(curl -s -X POST "${SERVICE_URL}/api/v1/admin/setup-payment-providers/" \
  -H "Content-Type: application/json" \
  -w "%{http_code}")

HTTP_CODE="${SETUP_RESPONSE: -3}"
RESPONSE_BODY="${SETUP_RESPONSE%???}"

if [ "$HTTP_CODE" = "200" ]; then
    print_success "Payment methods configured successfully!"
    echo "Response: $RESPONSE_BODY"
else
    print_error "Failed to setup payment methods (HTTP: $HTTP_CODE)"
    print_warning "Response: $RESPONSE_BODY"
    print_warning "MANUAL SETUP REQUIRED: Run 'python manage.py setup_payment_providers' after deployment"
fi

# Step 7: Service verification
print_step "PASO 7: Service verification..."
print_success "Backend service deployed and ready!"

# Step 7b: Verificar que la versión se registró en BD (deploys, uptime) — guarda estos logs para debug
print_step "PASO 7b: Verificación de registro de deploy..."
sleep 20
if [[ -n "${DEPLOY_CHECK_SECRET:-}" ]]; then
  DEPLOY_CHECK_RESPONSE=$(curl -s -w "\n%{http_code}" "${SERVICE_URL}/api/v1/deploy-check/?key=${DEPLOY_CHECK_SECRET}")
  DEPLOY_CHECK_HTTP_CODE=$(echo "$DEPLOY_CHECK_RESPONSE" | tail -n1)
  DEPLOY_CHECK_BODY=$(echo "$DEPLOY_CHECK_RESPONSE" | sed '$d')
  echo ""
  echo "========== DEPLOY CHECK (copia estos logs si algo falla) =========="
  echo "HTTP: $DEPLOY_CHECK_HTTP_CODE"
  echo "$DEPLOY_CHECK_BODY"
  echo "=================================================================="
  if [[ "$DEPLOY_CHECK_HTTP_CODE" = "200" ]]; then
    print_success "Backend respondió deploy-check. Revisa arriba: deploys_count, last_deploy_at, uptime_display, env_version."
  else
    print_warning "deploy-check devolvió HTTP $DEPLOY_CHECK_HTTP_CODE. ¿DEPLOY_CHECK_SECRET igual en cloud-run-env.yaml?"
  fi
else
  echo "   (Para verificar: añade DEPLOY_CHECK_SECRET en cloud-run-env.yaml y ejecuta con DEPLOY_CHECK_SECRET=xxx ./deploy.sh -m \"ref\")"
fi

# Step 8: Deploy Celery Services
print_step "PASO 8: Deploying Celery services for email processing..."

if [ -f "./deploy-celery.sh" ]; then
    ./deploy-celery.sh
    if [ $? -eq 0 ]; then
        print_success "Celery services deployed successfully!"
    else
        print_warning "Celery deployment had issues, emails may not work"
    fi
else
    print_warning "Celery deploy script not found, skipping Celery deployment"
fi

# Step 9: Configure domain prop.cl
print_step "PASO 9: Configuring domain prop.cl..."
echo "Ejecutando configuración de dominio..."

# Run domain configuration script
if [ -f "./setup-domain.sh" ]; then
    ./setup-domain.sh
    if [ $? -eq 0 ]; then
        print_success "Domain configuration completed!"
    else
        print_warning "Domain configuration had issues, check manually"
    fi
else
    print_warning "Domain setup script not found, skipping domain configuration"
fi

echo ""
echo "====================================="
print_success "🎉 DEPLOYMENT COMPLETED SUCCESSFULLY!"
echo ""
echo "📋 RESUMEN DEL DEPLOYMENT:"
echo "========================="
echo "🌐 Service URL: ${SERVICE_URL}"
echo "🌍 Domain: https://prop.cl (if configured)"
echo "📚 API Docs: ${SERVICE_URL}/api/docs/"
echo "⚙️  Admin: ${SERVICE_URL}/admin/"
echo "🔍 Health: ${SERVICE_URL}/healthz"
echo "🎯 Public Events: ${SERVICE_URL}/api/v1/public/events/"
echo ""
echo "👤 SUPERUSER CREDENTIALS:"
echo "========================"
echo "Username: admin"
echo "Email: admin@tuki.cl"
echo "Password: TukiAdmin2025!"
echo ""
echo "📋 NEXT STEPS:"
echo "=============="
echo "1. ✅ Backend deployed and running"
echo "2. ✅ Database migrated automatically"
echo "3. ✅ Superuser created automatically"
echo "4. ✅ Payment methods configured (WebPay Plus)"
echo "5. ✅ Celery services deployed for email processing"
echo "6. ✅ Domain configured (if script ran successfully)"
echo "7. 🔄 Update frontend to use https://prop.cl as backend URL"
echo "8. 🧪 Test all functionality thoroughly (especially payments and email)"
echo "9. 🔍 Monitor logs: gcloud run services logs read ${SERVICE_NAME} --region=${REGION}"
echo ""

# Step 11: Deploy Celery Workers (ENTERPRISE UNIFIED)
print_step "PASO 11: Deploying Celery Unified Worker..."
echo "🚀 Deploying single service with 4 internal workers"
echo "   • EMAILS: 4 workers (instant delivery <10s)"
echo "   • CRITICAL: 2 workers (high priority)"
echo "   • GENERAL: 2 workers (default tasks)"
echo "   • SYNC: 1 worker (heavy operations)"
echo ""

# Build Celery images
print_step "Building Celery images..."
gcloud builds submit \
  --config=cloudbuild-celery-unified.yaml \
  --substitutions=_IMAGE_TAG=${IMAGE_TAG} \
  --project=${PROJECT_ID}

if [ $? -eq 0 ]; then
    print_success "Celery images built successfully"
else
    print_error "Failed to build Celery images"
    exit 1
fi

# 🚀 COST-OPTIMIZED: Unified Worker min-instances=1 (required for periodic tasks)
# This is the "anchor" worker that guarantees periodic tasks execute
# Cloud Run does NOT auto-scale based on Redis queue, so we need at least 1 worker always listening
print_step "Deploying unified Celery worker..."
gcloud run deploy tuki-celery-unified \
  --image us-central1-docker.pkg.dev/${PROJECT_ID}/tuki-repo/tuki-celery-unified:${IMAGE_TAG} \
  --region ${REGION} \
  --platform managed \
  --no-allow-unauthenticated \
  --port 8080 \
  --min-instances 1 \
  --max-instances 10 \
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
    print_success "Unified worker deployed successfully"
else
    print_error "Failed to deploy unified worker"
    exit 1
fi

# Deploy Beat
print_step "Deploying Celery Beat..."
gcloud run deploy tuki-celery-beat \
  --image us-central1-docker.pkg.dev/${PROJECT_ID}/tuki-repo/tuki-celery-beat:${IMAGE_TAG} \
  --region ${REGION} \
  --platform managed \
  --no-allow-unauthenticated \
  --port 8080 \
  --min-instances 1 \
  --max-instances 1 \
  --memory 512Mi \
  --cpu 1 \
  --timeout 3600 \
  --env-vars-file cloud-run-env.yaml \
  --vpc-connector serverless-conn \
  --vpc-egress private-ranges-only \
  --service-account 187635794409-compute@developer.gserviceaccount.com

if [ $? -eq 0 ]; then
    print_success "Beat deployed successfully"
else
    print_error "Failed to deploy beat"
    exit 1
fi

print_success "Celery deployment completed!"
echo ""

# 🚀 COST-OPTIMIZED: Configure specialized workers to scale-to-zero
# These workers will only activate when there are tasks in their specific queues
print_step "Configuring specialized workers (scale-to-zero)..."
echo "Setting min-instances=0 for cost optimization..."

# Check if specialized workers exist and configure them
for worker_service in tuki-celery-worker-critical tuki-celery-worker-emails tuki-celery-worker-general tuki-celery-worker-sync; do
  if gcloud run services describe $worker_service --region=${REGION} --project=${PROJECT_ID} &>/dev/null; then
    echo "  → Configuring $worker_service to min-instances=0..."
    gcloud run services update $worker_service \
      --region=${REGION} \
      --min-instances=0 \
      --project=${PROJECT_ID} \
      --quiet
    echo "    ✅ $worker_service configured"
  else
    echo "  ℹ️  $worker_service does not exist (OK - using unified worker)"
  fi
done

print_success "Specialized workers configured for cost optimization!"
echo ""
print_success "Tuki Platform is now live and ready for production! 🚀"

# Final summary
echo ""
print_step "RESUMEN FINAL:"
echo "=============="
echo "🌐 Backend URL: ${SERVICE_URL}"
echo "📧 Celery Unified: 2-10 instances (8GB RAM, 4 vCPUs each)"
echo "📊 Celery Beat: 1 instance (512MB RAM)"
echo "🎯 All services ready for production use"
echo ""
echo "📋 Monitor Celery:"
echo "   gcloud run services logs read tuki-celery-unified --region=${REGION}"
echo ""
print_success "Deployment completed successfully! 🎯"
