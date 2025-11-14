# 🔧 Fix: API Organizer Endpoints (Error 405 y 404)

## Problema Reportado

En producción, al intentar editar datos de organizador se producían los siguientes errores:

1. **Error 405** en `PATCH /api/v1/organizers/current/`
   - El frontend enviaba PATCH pero el backend respondía: "Método PATCH no permitido"

2. **Error 404** en `GET /api/v1/organizers/dashboard-stats/?days=14`
   - El endpoint no estaba accesible

3. **Error 405** en `GET /api/v1/auth/organizer/profile/setup/`
   - Error transitorio de método no permitido

## Causa Raíz

El archivo `backtuki/api/v1/organizers/urls.py` existía con las rutas correctas definidas:
- `CurrentOrganizerView` (RetrieveUpdateAPIView) que soporta GET, PUT, PATCH
- Pero **NO estaba incluido** en el archivo principal de URLs (`backtuki/api/v1/urls.py`)

Como resultado:
- Las peticiones estaban siendo capturadas por el `OrganizerViewSet` registrado en el router
- El ViewSet solo tenía una acción personalizada `@action(detail=False, methods=['get'])` para `/organizers/current/`
- Por eso solo permitía GET, rechazando PATCH con error 405

## Solución Implementada

### 1. Incluir `api.v1.organizers.urls` en URLs principales

**Archivo:** `backtuki/api/v1/urls.py`

```python
urlpatterns = [
    # ⚠️ IMPORTANTE: Incluir organizers.urls ANTES del router para que tenga prioridad
    path('', include('api.v1.organizers.urls')),  # 🚀 Organizer profile management
    path('', include(router.urls)),
    # ... resto de URLs
]
```

**Por qué ANTES del router:**
- Django procesa las URLs en orden
- Si el router va primero, captura `/organizers/current/` con el ViewSet (solo GET)
- Al poner `organizers.urls` primero, las rutas específicas tienen prioridad

### 2. Crear vista independiente para Dashboard Stats

**Archivo:** `backtuki/api/v1/organizers/views.py`

Agregamos `DashboardStatsView` como clase APIView independiente:
- Permisos: `IsAuthenticated`, `IsOrganizer`
- Método: GET
- Funcionalidad completa de estadísticas del organizador

### 3. Agregar ruta para Dashboard Stats

**Archivo:** `backtuki/api/v1/organizers/urls.py`

```python
urlpatterns = [
    # ...
    path('organizers/current/', CurrentOrganizerView.as_view(), name='current_organizer'),
    path('organizers/dashboard-stats/', DashboardStatsView.as_view(), name='organizer_dashboard_stats'),
]
```

## Endpoints Ahora Funcionales

### ✅ `/api/v1/organizers/current/`
- **GET**: Obtener perfil del organizador actual
- **PUT**: Actualizar perfil completo
- **PATCH**: Actualizar perfil parcial ← **ARREGLADO**

### ✅ `/api/v1/organizers/dashboard-stats/`
- **GET**: Obtener estadísticas del dashboard
- Query params: `?days=14` (opcional)
- Respuesta: tickets vendidos, revenue, trends, daily data ← **ARREGLADO**

### ✅ `/api/v1/auth/organizer/profile/setup/`
- **GET**: Verificar si el perfil necesita configuración
- **POST**: Completar configuración inicial del perfil
- Ya estaba correctamente configurado

## Archivos Modificados

1. `backtuki/api/v1/urls.py` - Incluir organizers.urls
2. `backtuki/api/v1/organizers/views.py` - Agregar DashboardStatsView
3. `backtuki/api/v1/organizers/urls.py` - Agregar ruta dashboard-stats

## Deployment a Producción

### Opción 1: Deploy Manual

```bash
cd backtuki

# Verificar cambios
git diff

# Commitear cambios
git add api/v1/urls.py api/v1/organizers/urls.py api/v1/organizers/views.py
git commit -m "🔧 Fix: Habilitar PATCH en /organizers/current/ y agregar dashboard-stats endpoint"

# Push a producción
git push origin main

# En el servidor de producción, hacer pull y restart
# (Dependiendo de tu configuración de deployment)
```

### Opción 2: Cloud Run (Automático)

Si tienes CI/CD configurado con Cloud Build:

```bash
cd backtuki
git add api/v1/urls.py api/v1/organizers/urls.py api/v1/organizers/views.py
git commit -m "🔧 Fix: Habilitar PATCH en /organizers/current/ y agregar dashboard-stats endpoint"
git push origin main

# Cloud Build detectará el push y hará deploy automático
```

### Verificación Post-Deploy

1. **Test de PATCH:**
```bash
curl -X PATCH 'https://prop.cl/api/v1/organizers/current/' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"name": "Test Organization"}'
```

2. **Test de Dashboard Stats:**
```bash
curl 'https://prop.cl/api/v1/organizers/dashboard-stats/?days=14' \
  -H 'Authorization: Bearer YOUR_TOKEN'
```

Ambos deberían responder con 200 OK.

## Notas Técnicas

### Por qué este bug pasó desapercibido

1. En desarrollo local probablemente funcionaba porque el orden de imports podía ser diferente
2. El ViewSet estaba registrado en el router, creando una ruta con el mismo path pero con diferentes métodos permitidos
3. Sin tests automatizados para los métodos HTTP específicos, el error solo apareció en producción

### Prevención Futura

Consideraciones para evitar este tipo de problemas:

1. **Tests de integración** que verifiquen métodos HTTP específicos:
```python
def test_organizer_current_allows_patch():
    response = client.patch('/api/v1/organizers/current/', data={...})
    assert response.status_code != 405
```

2. **Documentación clara** de qué ViewSets están en el router vs. qué rutas están en archivos específicos

3. **Linting de URLs** para detectar rutas duplicadas o conflictivas

## Impacto

- **Usuarios afectados**: Organizadores que intentaban editar su perfil
- **Severidad**: Alta (funcionalidad crítica bloqueada)
- **Duración**: Desde el último deploy hasta ahora
- **Solución**: Deploy inmediato recomendado

---

**Fecha:** 2025-11-04
**Estado:** ✅ Arreglado - Pendiente deploy a producción

