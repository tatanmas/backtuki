#!/bin/bash

# 🎯 EVENT MODE DEPLOYMENT - Tuki Platform
# =========================================
# Use this script to pre-scale for large events (1000+ simultaneous users)
#
# What it does:
# - Increases min-instances for backend and workers
# - Prepares infrastructure for high load
#
# IMPORTANT: After the event, run: ./deploy.sh to return to cost-optimized mode

set -e

# Configuration
PROJECT_ID="tukiprod"
REGION="us-central1"

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

echo ""
echo "🎯 =========================================="
echo "🎯 TUKI PLATFORM - EVENT MODE DEPLOYMENT"
echo "🎯 =========================================="
echo ""
print_warning "This will increase min-instances for HIGH LOAD events (1000+ users)"
print_warning "Estimated cost during event: ~$50-70k CLP/month"
echo ""
read -p "Continue? (y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    print_error "Deployment cancelled"
    exit 1
fi

# Step 1: Scale Backend
print_step "STEP 1: Scaling backend for high load..."
gcloud run services update tuki-backend \
  --region=${REGION} \
  --min-instances=3 \
  --project=${PROJECT_ID}

if [ $? -eq 0 ]; then
    print_success "Backend scaled to min=3 instances"
else
    print_error "Failed to scale backend"
    exit 1
fi

# Step 2: Scale Celery Workers
print_step "STEP 2: Scaling Celery workers for high load..."

# Unified worker
gcloud run services update tuki-celery-unified \
  --region=${REGION} \
  --min-instances=3 \
  --project=${PROJECT_ID}

if [ $? -eq 0 ]; then
    print_success "Unified worker scaled to min=3 instances"
else
    print_warning "Failed to scale unified worker (may not exist)"
fi

# Specialized workers (if they exist)
for worker_service in tuki-celery-worker tuki-celery-worker-emails tuki-celery-worker-general; do
  if gcloud run services describe $worker_service --region=${REGION} --project=${PROJECT_ID} &>/dev/null; then
    echo "  → Scaling $worker_service to min=2..."
    gcloud run services update $worker_service \
      --region=${REGION} \
      --min-instances=2 \
      --project=${PROJECT_ID} \
      --quiet
    echo "    ✅ $worker_service scaled"
  fi
done

print_success "All workers scaled for event mode!"

# Step 3: Instructions for Cloud SQL (manual)
echo ""
print_step "STEP 3: Cloud SQL Optimization (OPTIONAL - Manual)"
echo "For CRITICAL events, consider temporarily enabling Regional HA:"
echo ""
echo "  gcloud sql instances patch tuki-db-prod \\"
echo "    --availability-type=REGIONAL \\"
echo "    --region=us-central1 \\"
echo "    --project=${PROJECT_ID}"
echo ""
print_warning "This adds ~$7k/month but provides automatic failover"
print_warning "Only do this if downtime during event would be catastrophic"
echo ""

# Summary
echo ""
print_success "🎯 EVENT MODE ACTIVATED!"
echo ""
echo "📋 Current Configuration:"
echo "  • Backend: min=3 instances (was 1)"
echo "  • Workers: min=2-3 instances per service (was 0-1)"
echo "  • Cloud SQL: Check if you need Regional HA (manual)"
echo ""
echo "⏰ After the event finishes:"
echo "  Run: ./deploy.sh"
echo "  This will return to cost-optimized configuration"
echo ""
print_success "Platform ready for high-load event! 🚀"

