#!/bin/bash

# 🚀 ENTERPRISE DOMAIN SETUP - prop.cl Configuration
# Tuki Platform - Configuración completa de dominio para Google Cloud Run

set -e

# Configuration
PROJECT_ID="tukiprod"
REGION="us-central1"
DOMAIN="prop.cl"
SERVICE_NAME="tuki-backend"
BACKEND_SERVICE_NAME="tuki-backend-enterprise"
NEG_NAME="tuki-api-neg-final"

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

echo "🚀 CONFIGURING DOMAIN prop.cl FOR TUKI PLATFORM"
echo "=============================================="

# Step 1: Check current configuration
print_step "Checking current domain configuration..."

# Get current service URL
SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --region=${REGION} --format="value(status.url)" 2>/dev/null || echo "")

if [ -z "$SERVICE_URL" ]; then
    print_error "Service ${SERVICE_NAME} not found. Please deploy the service first."
    exit 1
fi

print_success "Found service: ${SERVICE_URL}"

# Step 2: Update Network Endpoint Group to point to correct service
print_step "Updating Network Endpoint Group to point to ${SERVICE_NAME}..."

# Check if NEG exists
if gcloud compute network-endpoint-groups describe ${NEG_NAME} --region=${REGION} >/dev/null 2>&1; then
    print_warning "NEG ${NEG_NAME} exists. Updating to point to ${SERVICE_NAME}..."
    
    # Delete existing NEG
    gcloud compute network-endpoint-groups delete ${NEG_NAME} --region=${REGION} --quiet
    print_success "Deleted existing NEG"
fi

# Create new NEG pointing to the correct service
print_step "Creating new Network Endpoint Group..."
gcloud compute network-endpoint-groups create ${NEG_NAME} \
    --region=${REGION} \
    --network-endpoint-type=serverless \
    --cloud-run-service=${SERVICE_NAME}

print_success "Created NEG pointing to ${SERVICE_NAME}"

# Step 3: Create or update Backend Service
print_step "Setting up Backend Service..."

# Check if backend service exists
if gcloud compute backend-services describe ${BACKEND_SERVICE_NAME} --global >/dev/null 2>&1; then
    print_warning "Backend service ${BACKEND_SERVICE_NAME} exists. Updating..."
    
    # Remove existing backends
    gcloud compute backend-services remove-backend ${BACKEND_SERVICE_NAME} \
        --global \
        --network-endpoint-group=${NEG_NAME} \
        --network-endpoint-group-region=${REGION} \
        --quiet 2>/dev/null || true
else
    # Create new backend service
    print_step "Creating new Backend Service..."
    gcloud compute backend-services create ${BACKEND_SERVICE_NAME} \
        --global \
        --protocol=HTTP \
        --load-balancing-scheme=EXTERNAL_MANAGED
    
    print_success "Created backend service"
fi

# Add the NEG as backend
print_step "Adding NEG as backend..."
gcloud compute backend-services add-backend ${BACKEND_SERVICE_NAME} \
    --global \
    --network-endpoint-group=${NEG_NAME} \
    --network-endpoint-group-region=${REGION}

print_success "Backend service configured successfully"

# Step 4: Verify URL Map configuration
print_step "Verifying URL Map configuration..."

# The URL map should already be configured for prop.cl, but let's verify
URL_MAP_CONFIG=$(gcloud compute url-maps describe tuki-url-map --format="value(hostRules[].hosts[])" | grep -c "prop.cl" || echo "0")

if [ "$URL_MAP_CONFIG" = "0" ]; then
    print_error "prop.cl not found in URL map. Manual configuration needed."
    echo "Current URL map configuration:"
    gcloud compute url-maps describe tuki-url-map --format="yaml(hostRules)"
else
    print_success "prop.cl is configured in URL map"
fi

# Step 5: Test the configuration
print_step "Testing domain configuration..."

# Wait a moment for changes to propagate
sleep 10

# Test HTTP access
print_step "Testing HTTP access to prop.cl..."
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "http://prop.cl/healthz" || echo "000")

if [ "$HTTP_STATUS" = "200" ]; then
    print_success "HTTP access working!"
elif [ "$HTTP_STATUS" = "301" ] || [ "$HTTP_STATUS" = "302" ]; then
    print_success "HTTP redirecting to HTTPS (expected)"
else
    print_warning "HTTP returned status: $HTTP_STATUS"
fi

# Test HTTPS access
print_step "Testing HTTPS access to prop.cl..."
HTTPS_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "https://prop.cl/healthz" || echo "000")

if [ "$HTTPS_STATUS" = "200" ]; then
    print_success "HTTPS access working!"
else
    print_warning "HTTPS returned status: $HTTPS_STATUS"
fi

# Test API endpoints
print_step "Testing API endpoints..."

# Test public events API
API_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "https://prop.cl/api/v1/public/events/" || echo "000")
if [ "$API_STATUS" = "200" ]; then
    print_success "Public events API working!"
else
    print_warning "Public events API returned status: $API_STATUS"
fi

# Test admin interface
ADMIN_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "https://prop.cl/admin/" || echo "000")
if [ "$ADMIN_STATUS" = "302" ] || [ "$ADMIN_STATUS" = "200" ]; then
    print_success "Admin interface accessible!"
else
    print_warning "Admin interface returned status: $ADMIN_STATUS"
fi

echo ""
echo "=============================================="
print_success "DOMAIN CONFIGURATION COMPLETED!"
echo ""
echo "🌐 Domain: https://prop.cl"
echo "🔍 Health: https://prop.cl/healthz"
echo "📚 API Docs: https://prop.cl/api/docs/"
echo "⚙️  Admin: https://prop.cl/admin/"
echo "🎯 Public Events: https://prop.cl/api/v1/public/events/"
echo ""

if [ "$HTTPS_STATUS" = "200" ] && [ "$API_STATUS" = "200" ]; then
    print_success "🎉 prop.cl is now fully functional!"
    echo ""
    echo "📋 Next steps:"
    echo "1. Update frontend configuration to use https://prop.cl as backend URL"
    echo "2. Test all API endpoints thoroughly"
    echo "3. Verify SSL certificate is working correctly"
    echo "4. Monitor logs for any issues"
else
    print_warning "⚠️  Some endpoints may need additional time to propagate"
    echo ""
    echo "🔧 Troubleshooting:"
    echo "1. Wait 5-10 minutes for DNS/SSL propagation"
    echo "2. Check Cloud Run service logs: gcloud run services logs read ${SERVICE_NAME} --region=${REGION}"
    echo "3. Verify backend service health: gcloud compute backend-services get-health ${BACKEND_SERVICE_NAME} --global"
fi

echo ""
print_success "Domain setup script completed! 🚀"
