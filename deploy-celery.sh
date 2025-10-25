#!/bin/bash

# 🚀 ENTERPRISE CELERY DEPLOYMENT - Tuki Platform
# Deploys Celery Worker and Beat services to Google Cloud Run
# Designed to be robust and production-ready

set -e

# Configuration
PROJECT_ID="tukiprod"
REGION="us-central1"
IMAGE_TAG="v1-production"
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

echo "🚀 TUKI CELERY - ENTERPRISE DEPLOYMENT"
echo "====================================="
echo ""

# Step 1: Build Celery images
print_step "PASO 1: Building Celery images..."
gcloud builds submit --config cloudbuild-celery.yaml --substitutions _IMAGE_TAG=${IMAGE_TAG}

if [ $? -eq 0 ]; then
    print_success "Celery images built and pushed successfully!"
else
    print_error "Failed to build Celery images"
    exit 1
fi

# Step 2: Deploy Celery Worker
print_step "PASO 2: Deploying Celery Worker..."

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
  --service-account 187635794409-compute@developer.gserviceaccount.com

if [ $? -eq 0 ]; then
    print_success "Celery Worker deployed successfully!"
else
    print_error "Failed to deploy Celery Worker"
    exit 1
fi

# Step 3: Deploy Celery Beat
print_step "PASO 3: Deploying Celery Beat..."

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
  --service-account 187635794409-compute@developer.gserviceaccount.com

if [ $? -eq 0 ]; then
    print_success "Celery Beat deployed successfully!"
else
    print_error "Failed to deploy Celery Beat"
    exit 1
fi

# Step 4: Wait for services to stabilize
print_step "PASO 4: Waiting for Celery services to stabilize..."
sleep 30

# Get service URLs for reference
WORKER_URL=$(gcloud run services describe ${WORKER_SERVICE_NAME} --region=${REGION} --format="value(status.url)")
BEAT_URL=$(gcloud run services describe ${BEAT_SERVICE_NAME} --region=${REGION} --format="value(status.url)")

print_success "Celery services deployed and stabilizing!"
print_success "Worker URL: ${WORKER_URL}"
print_success "Beat URL: ${BEAT_URL}"

# Step 5: Test email functionality
print_step "PASO 5: Testing email functionality..."

# Get backend URL
BACKEND_URL=$(gcloud run services describe tuki-backend --region=${REGION} --format="value(status.url)")

# Test if we can queue an email task (this would require a test endpoint)
print_warning "Manual email test required - create a test order to verify email sending"

echo ""
echo "====================================="
print_success "🎉 CELERY DEPLOYMENT COMPLETED!"
echo ""
echo "📋 CELERY DEPLOYMENT SUMMARY:"
echo "============================"
echo "🔧 Worker URL: ${WORKER_URL}"
echo "📅 Beat URL: ${BEAT_URL}"
echo "🌐 Backend URL: ${BACKEND_URL}"
echo ""
echo "📋 NEXT STEPS:"
echo "=============="
echo "1. ✅ Celery Worker deployed and running"
echo "2. ✅ Celery Beat deployed and running"
echo "3. 🧪 Test email functionality by creating a test order"
echo "4. 🔍 Monitor logs: gcloud run services logs read ${WORKER_SERVICE_NAME} --region=${REGION}"
echo "5. 🔍 Monitor logs: gcloud run services logs read ${BEAT_SERVICE_NAME} --region=${REGION}"
echo ""
print_success "Celery services are now live and ready for email processing! 📧"
