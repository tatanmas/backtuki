# 🧪 Prueba del Sistema de Carga

Este archivo documenta las pruebas del sistema de carga de contenido.

## Datos de prueba creados

### Tour de prueba: `test-tour-santiago`

**Ubicación**: `carga/tours/test-tour-santiago/`

**Archivos**:
- `descripcion.txt`: Descripción completa del tour
- `datos.json`: Configuración (horarios, capacidad, ubicación, etc.)
- `imagenes/`: Carpeta para imágenes (vacía por ahora, usar imágenes placeholder)

**Organizador de prueba**: Se debe obtener con `carga/ai_helpers/get_organizers.py --active`

---

## Pasos para probar

### 1. Obtener lista de organizadores

```bash
cd /Users/sebamasretamal/Desktop/cursor/tukifull/backtuki
python ../carga/ai_helpers/get_organizers.py --active
```

**Resultado esperado**: JSON con organizadores y sus IDs

### 2. Ver estructura del modelo Experience

```bash
cd /Users/sebamasretamal/Desktop/cursor/tukifull/backtuki
python ../carga/ai_helpers/extract_model_schema.py Experience
```

**Resultado esperado**: JSON con todos los campos del modelo

### 3. Procesar insumos de prueba (sin imágenes por ahora)

```bash
cd /Users/sebamasretamal/Desktop/cursor/tukifull

python carga/process_insumo.py \
  --type tour \
  --input carga/tours/test-tour-santiago/ \
  --organizer <ORGANIZER_ID_DEL_PASO_1> \
  --output carga/tours/test-tour-santiago/payload.json
```

**Resultado esperado**: 
- Archivo `payload.json` generado
- Log mostrando título, descripción, categorías extraídas
- Advertencia sobre imágenes faltantes

### 4. Validar payload localmente

```bash
cd /Users/sebamasretamal/Desktop/cursor/tukifull/backtuki
python ../carga/ai_helpers/validate_payload.py experience ../carga/tours/test-tour-santiago/payload.json
```

**Resultado esperado**: 
- `{"valid": true, "message": "Payload is valid"}`
- Exit code 0

### 5. (Opcional) Subir experiencia al backend

⚠️ **ADVERTENCIA**: Este paso requiere credenciales de superadmin y subirá datos reales al backend.

```bash
export TUKI_API_URL=https://tuki.cl/api/v1
export TUKI_SUPERADMIN_TOKEN=<tu_token_jwt>

python carga/upload_experience.py carga/tours/test-tour-santiago/payload.json
```

**Resultado esperado**:
- Experiencia creada en backend
- ID y slug generados
- Instancias creadas según recurrence_pattern
- URL del frontend para verificar

---

## Pruebas con imágenes (cuando tengas acceso)

### 1. Agregar imágenes de prueba

Copia algunas imágenes a `carga/tours/test-tour-santiago/imagenes/`:

```bash
# Ejemplo: copiar imágenes de placeholder
cp ~/Downloads/santiago-*.jpg carga/tours/test-tour-santiago/imagenes/
```

### 2. Subir imágenes a media library

```bash
export TUKI_API_URL=https://tuki.cl/api/v1
export TUKI_SUPERADMIN_TOKEN=<tu_token>

python carga/upload_media.py \
  carga/tours/test-tour-santiago/imagenes/*.jpg \
  --organizer <ORGANIZER_ID> \
  --output carga/tours/test-tour-santiago/media_ids.json
```

**Resultado esperado**:
- Archivo `media_ids.json` con IDs y URLs de MediaAssets
- Log mostrando cada imagen subida exitosamente

### 3. Regenerar payload con imágenes reales

```bash
python carga/process_insumo.py \
  --type tour \
  --input carga/tours/test-tour-santiago/ \
  --organizer <ORGANIZER_ID> \
  --media-file carga/tours/test-tour-santiago/media_ids.json \
  --output carga/tours/test-tour-santiago/payload.json
```

**Resultado esperado**:
- Payload actualizado con URLs reales de imágenes
- Sin advertencias sobre imágenes faltantes

### 4. Validar y subir

```bash
# Validar
cd backtuki
python ../carga/ai_helpers/validate_payload.py experience ../carga/tours/test-tour-santiago/payload.json

# Subir
cd ..
python carga/upload_experience.py carga/tours/test-tour-santiago/payload.json
```

---

## Checklist de validación

### Scripts helper funcionan
- [ ] `extract_model_schema.py Experience` devuelve JSON con campos
- [ ] `get_organizers.py --active` devuelve lista de organizadores
- [ ] `validate_payload.py experience payload.json` valida correctamente
- [ ] `list_endpoints.py experience` muestra endpoints
- [ ] `inspect_destination.py <slug>` devuelve destino (si existe alguno)

### Procesamiento de insumos
- [ ] `process_insumo.py` extrae título de descripcion.txt
- [ ] `process_insumo.py` extrae descripción completa
- [ ] `process_insumo.py` merge con datos.json correctamente
- [ ] `process_insumo.py` genera slug automáticamente
- [ ] `process_insumo.py` genera payload.json válido

### Upload (con credenciales)
- [ ] `upload_media.py` sube imágenes y devuelve IDs/URLs
- [ ] `upload_experience.py` crea experiencia en backend
- [ ] Experiencia visible en frontend
- [ ] Instancias generadas según recurrence_pattern
- [ ] Imágenes se muestran correctamente en frontend

### WhatsApp (opcional, si es experiencia con WhatsApp)
- [ ] `configure_whatsapp.py` configura operador
- [ ] Reservas por WhatsApp funcionan

---

## Estado actual

- ✅ Documentación creada (AI_HELPERS, PLATAFORMA_CONTENIDO, ESTANDARES_CODIGO)
- ✅ Estructura de carpetas `carga/` con subcarpetas
- ✅ Scripts helper (ai_helpers/) implementados
- ✅ Scripts de procesamiento y upload implementados
- ✅ Plantilla JSON de referencia (_plantilla.json)
- ✅ Datos de prueba creados (test-tour-santiago)
- ⏳ Pendiente: Probar con credenciales reales

---

**Última actualización**: 2026-02-10  
**Próximo paso**: Probar con credenciales de superadmin y validar que todo funcione end-to-end
