#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# Auditoría: URLs de medios en Dako (ejecutar EN el servidor o via: dako "bash -s" < backtuki/scripts/audit-media-urls-dako.sh)
# ═══════════════════════════════════════════════════════════════════════════════
set -e
echo "════════════════════════════════════════════════════════════════"
echo "🔍 AUDITORÍA MEDIA URLS - DAKO"
echo "════════════════════════════════════════════════════════════════"
echo ""

echo "1️⃣ BACKEND_URL en contenedor:"
docker exec tuki-backend env | grep -E '^BACKEND_URL=' || echo "   ❌ BACKEND_URL no definido"
echo ""

echo "2️⃣ Código en contenedor: ¿MediaAsset usa BACKEND_URL?"
docker exec tuki-backend grep -n "BACKEND_URL\|localhost:8000" /app/apps/media/models.py 2>/dev/null | head -20 || echo "   (no se pudo leer)"
echo ""

echo "3️⃣ Serializer: ¿prefer BACKEND_URL?"
docker exec tuki-backend grep -A2 "def get_url" /app/apps/media/serializers.py 2>/dev/null | head -10 || echo "   (no se pudo leer)"
echo ""

echo "4️⃣ Respuesta API media (primer asset):"
# Sin auth devuelve 401; si tienes token puedes hacer: curl -s -H "Authorization: Bearer TOKEN" https://tuki.cl/api/v1/media/assets/?page_size=1
# Desde dentro del servidor podemos curl al backend por nombre
API_JSON=$(docker exec tuki-backend curl -s -H "Accept: application/json" "http://localhost:8080/api/v1/media/assets/?page_size=1" 2>/dev/null || true)
if echo "$API_JSON" | grep -q "results"; then
  FIRST_URL=$(echo "$API_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); r=d.get('results',[]); print(r[0]['url'] if r else '')" 2>/dev/null || echo "")
  if [ -n "$FIRST_URL" ]; then
    echo "   URL en API: $FIRST_URL"
    if echo "$FIRST_URL" | grep -q "localhost"; then
      echo "   ❌ Sigue devolviendo localhost"
    else
      echo "   ✅ URL correcta (no localhost)"
    fi
  else
    echo "   (no hay results o no se pudo parsear)"
  fi
else
  echo "   (API requiere auth o no respondió; status: $(echo "$API_JSON" | head -c 200))"
fi
echo ""

echo "5️⃣ Django settings BACKEND_URL (desde shell):"
docker exec tuki-backend python -c "
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.homeserver')
import django
django.setup()
from django.conf import settings
print('   BACKEND_URL =', repr(getattr(settings, 'BACKEND_URL', None)))
print('   DEFAULT_FILE_STORAGE =', getattr(settings, 'DEFAULT_FILE_STORAGE', ''))
" 2>/dev/null || echo "   (error al cargar Django)"
echo ""

echo "════════════════════════════════════════════════════════════════"
echo "Si BACKEND_URL está bien y el código tiene BACKEND_URL pero la API"
echo "sigue devolviendo localhost, reinicia el backend:"
echo "   docker-compose restart tuki-backend"
echo "Si el código en el contenedor no tiene BACKEND_URL, redeploy con:"
echo "   ./deploy-dako.sh --skip-git-pull --no-cache"
echo "════════════════════════════════════════════════════════════════"
