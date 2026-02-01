#!/bin/bash

# 🔧 PREPARAR GCLOUD EN TU MAC
# Script para verificar y configurar gcloud en tu Mac antes de ejecutar migración

set -euo pipefail

PROJECT_ID="tukiprod"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_step() { echo -e "${BLUE}🔧 $1${NC}"; }
print_success() { echo -e "${GREEN}✅ $1${NC}"; }
print_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
print_error() { echo -e "${RED}❌ $1${NC}"; }
print_info() { echo -e "${BLUE}ℹ️  $1${NC}"; }

echo "🔧 PREPARAR GCLOUD EN TU MAC"
echo "============================="
echo ""

# Verificar gcloud instalado
if ! command -v gcloud &> /dev/null; then
    print_error "gcloud CLI no está instalado"
    print_info "Instala desde: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

print_success "gcloud CLI instalado: $(gcloud --version | head -1)"

# Verificar autenticación
print_step "Verificando autenticación..."

AUTH_ACCOUNTS=$(gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>/dev/null || echo "")

if [[ -z "$AUTH_ACCOUNTS" ]]; then
    print_warning "No estás autenticado"
    print_info "Ejecuta: gcloud auth login"
    exit 1
fi

print_success "Autenticado como: $AUTH_ACCOUNTS"

# Verificar que el token funciona
print_step "Verificando que el token es válido..."

if gcloud projects list --filter="projectId:$PROJECT_ID" --format="value(projectId)" 2>/dev/null | grep -q "$PROJECT_ID"; then
    print_success "Token válido y funcionando"
else
    print_warning "El token parece haber expirado"
    print_info "Necesitas refrescar la autenticación:"
    echo ""
    echo "  gcloud auth login"
    echo ""
    print_info "Esto abrirá tu navegador. Inicia sesión con tecnologia@tuki.cl"
    exit 1
fi

# Verificar proyecto
print_step "Verificando proyecto..."

CURRENT_PROJECT=$(gcloud config get-value project 2>/dev/null || echo "")

if [[ "$CURRENT_PROJECT" == "$PROJECT_ID" ]]; then
    print_success "Proyecto configurado: $PROJECT_ID"
else
    print_info "Configurando proyecto..."
    gcloud config set project "$PROJECT_ID"
    print_success "Proyecto configurado"
fi

# Verificar permisos
print_step "Verificando permisos..."

print_info "Verificando acceso a Cloud SQL..."
if gcloud sql instances describe tuki-db-prod --project="$PROJECT_ID" --format="value(name)" 2>/dev/null | grep -q "tuki-db-prod"; then
    print_success "Acceso a Cloud SQL: OK"
else
    print_error "No puedes acceder a Cloud SQL. Verifica permisos."
    exit 1
fi

print_info "Verificando acceso a Cloud Storage..."
if gsutil ls gs://tuki-media-prod-1759240560/ 2>/dev/null | head -1 | grep -q "gs://"; then
    print_success "Acceso a Cloud Storage: OK"
else
    print_error "No puedes acceder a Cloud Storage. Verifica permisos."
    exit 1
fi

echo ""
print_success "✅ Todo listo en tu Mac!"
echo ""
echo "📋 Ahora puedes ejecutar:"
echo "   ./paso2-service-account.sh"
echo ""

