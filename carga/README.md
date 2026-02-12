# 📂 Carpeta de insumos - Guía de uso

Esta carpeta es donde el agente IA busca contenido para procesar y subir a la plataforma Tuki. Soporta **múltiples formatos** y es flexible en cuanto a la organización.

---

## 📋 Estructura

```
carga/
├── README.md                   # Este archivo
├── tours/                      # Tours y experiencias tipo "tour"
│   ├── _plantilla.json         # Plantilla de referencia con todos los campos
│   └── <nombre-tour>/          # Carpeta por tour
│       ├── descripcion.txt     # Texto con descripción
│       ├── itinerario.pdf      # PDF con itinerario (opcional)
│       ├── datos.json          # JSON parcial (opcional)
│       └── imagenes/           # Carpeta con imágenes
│           ├── imagen1.jpg
│           └── imagen2.jpg
├── experiencias/               # Experiencias (actividades, workshops, etc.)
│   └── <nombre-experiencia>/
├── destinos/                   # Destinos (LandingDestination)
│   └── <nombre-destino>/
│       ├── info.txt            # Información general del destino
│       ├── guias/              # Guías de viaje para este destino
│       │   ├── guia-completa.pdf
│       │   └── ruta-gastronomica.md
│       └── imagenes/
│           ├── hero.jpg        # Imagen principal
│           └── galeria/
│               ├── img1.jpg
│               └── img2.jpg
├── guias/                      # Guías de viaje standalone
│   └── <nombre-guia>/
│       ├── contenido.pdf
│       └── cover.jpg
└── alojamientos/               # Alojamientos (cuando el modelo exista)
    └── <nombre-alojamiento>/
        ├── info.txt
        └── fotos/
```

---

## 🎯 Formatos soportados

### Texto
- **`.txt`**: Texto plano
- **`.md`**: Markdown (se parsea automáticamente)
- **Contenido**: Descripción, información general, itinerarios en texto

### PDFs
- **`.pdf`**: El agente extrae texto, títulos, itinerarios
- **Bibliotecas**: PyPDF2, pdfplumber
- **Uso**: Itinerarios detallados, guías de viaje, folletos

### Imágenes
- **Formatos**: `.jpg`, `.jpeg`, `.png`, `.webp`, `.gif`
- **Procesamiento**: 
  - Se suben a la media library del backend
  - Se redimensionan si son muy grandes
  - Se obtienen URLs o IDs para incluir en el payload
- **Nombres**: Descriptivos recomendado (ej: `valparaiso-hero.jpg`)

### JSON
- **`.json`**: Datos estructurados parciales o completos
- **Uso**: Si ya tienes parte de la estructura, el agente la completa
- **Formato**: Ver `_plantilla.json` en cada carpeta

### Web (futuro)
- **URLs**: Pasa una URL de Booking, Airbnb, etc.
- **Scraping**: El agente extrae información automáticamente
- **Formato**: Crear archivo `source.txt` con la URL

---

## 🚀 Flujo de trabajo

### Paso 1: Crear carpeta para el contenido

```bash
mkdir -p carga/tours/santiago-historico
```

### Paso 2: Agregar archivos

```bash
# Descripción en texto
echo "Tour Histórico por Santiago

Recorre los lugares más emblemáticos del centro histórico..." > carga/tours/santiago-historico/descripcion.txt

# Copiar imágenes
cp ~/Downloads/tour-*.jpg carga/tours/santiago-historico/imagenes/

# Opcional: JSON parcial con datos que ya tienes
cat > carga/tours/santiago-historico/datos.json << EOF
{
  "type": "tour",
  "duration_minutes": 120,
  "max_participants": 25
}
EOF
```

### Paso 3: Decirle al agente

> "Sube el tour de Santiago histórico, organizador Free Tours Santiago"

### Paso 4: El agente procesa

1. Lee `descripcion.txt` → extrae título y descripción
2. Parsea `itinerario.pdf` (si existe) → genera array de itinerario
3. Sube imágenes → obtiene URLs
4. Merge con `datos.json` (si existe)
5. Valida el payload localmente
6. Sube al backend con el script

### Paso 5: Verificar en el frontend

El agente te da la URL para revisar el tour en el frontend.

---

## 📝 Ejemplos

### Ejemplo 1: Tour con PDF de itinerario

```
carga/tours/valparaiso-walking/
├── descripcion.txt          # "Tour Walking por Valparaíso..."
├── itinerario.pdf           # PDF con paradas: Plaza Sotomayor, Cerro Alegre, etc.
└── imagenes/
    ├── valpo-1.jpg
    ├── valpo-2.jpg
    └── valpo-3.jpg
```

**Comando**:
> "Sube el tour de Valparaíso walking, organizador Tours Valpo"

### Ejemplo 2: Experiencia con JSON parcial

```
carga/experiencias/kayak-cochamó/
├── info.md                  # Markdown con descripción rica
├── datos.json               # {"type": "adventure", "duration_minutes": 240}
└── fotos/
    ├── kayak-1.jpg
    ├── kayak-2.jpg
    └── kayak-3.jpg
```

**Comando**:
> "Sube la experiencia de kayak en Cochamó, organizador Adventures Chile"

### Ejemplo 3: Destino con guías

```
carga/destinos/valparaiso/
├── info.txt                 # Descripción del destino
├── guias/
│   ├── guia-completa.pdf    # Guía turística completa
│   └── arte-callejero.md    # Guía de murales
└── imagenes/
    ├── hero.jpg             # Imagen principal
    └── galeria/
        ├── cerro-alegre.jpg
        └── ascensor.jpg
```

**Comando**:
> "Crea el destino Valparaíso con las guías que están en la carpeta"

### Ejemplo 4: Alojamiento desde URL (futuro)

```
carga/alojamientos/hostal-puerto-varas/
└── source.txt               # URL de Booking.com del hostal
```

**Comando**:
> "Carga este alojamiento desde Booking, scrapea la info"

---

## 🛠️ Scripts del agente

El agente usa estos scripts para procesar tus insumos:

### `process_insumo.py`

**Propósito**: Toma una carpeta de insumos y genera un JSON válido

**Uso**:
```bash
python scripts/process_insumo.py \
  --type tour \
  --input carga/tours/santiago-historico/ \
  --organizer 550e8400-e29b-41d4-a716-446655440000 \
  --output carga/tours/santiago-historico/payload.json
```

**Qué hace**:
- Lee todos los archivos de la carpeta
- Extrae información relevante (título, descripción, itinerario)
- Sube imágenes a media library
- Genera JSON completo y válido
- Guarda en `payload.json`

### `upload_experience.py`

**Propósito**: Sube el JSON al backend

**Uso**:
```bash
export TUKI_SUPERADMIN_TOKEN=<tu-token>
python scripts/upload_experience.py carga/tours/santiago-historico/payload.json
```

**Qué hace**:
- Valida el JSON localmente
- Llama a `/api/v1/superadmin/experiences/create-from-json/`
- Maneja errores y reintentos
- Te da el ID y URL del tour creado

---

## 📚 Referencias

### Plantilla JSON completa

Ver `carga/tours/_plantilla.json` para un ejemplo con todos los campos comentados.

### Documentación de la plataforma

- **Modelos y campos**: `docs/PLATAFORMA_CONTENIDO.md`
- **Helpers del agente**: `docs/AI_HELPERS.md`
- **Estándares de código**: `docs/ESTANDARES_CODIGO.md`

### Schemas de referencia

- **Experience JSON**: `tuki-experiencias/project_context/EXPERIENCE_JSON_REFERENCE.json`
- **Tour form schema**: `tuki-experiencias/TOUR_CREATION_SCHEMA.json`

---

## ⚠️ Notas importantes

### Organizer ID

Siempre necesitas especificar el organizador. Puedes:
1. Decirle al agente el nombre del organizador (ej: "Free Tours Santiago")
2. Pasar el UUID directamente
3. El agente ejecuta `get_organizers.py` para buscar el ID

### Slug

El slug se genera automáticamente del título, pero puedes especificarlo en `datos.json`:

```json
{
  "slug": "mi-slug-personalizado"
}
```

### Imágenes

**⚠️ IMPORTANTE**: Las imágenes se suben PRIMERO a la media library del backend, NO son URLs mockeadas.

**Flujo correcto**:
1. El agente ejecuta `upload_media.py` con las imágenes de tu carpeta
2. Obtiene IDs y URLs reales de MediaAsset
3. Usa esos IDs/URLs en el `experience_data`
4. Cuando subes la experiencia, las imágenes ya están en el backend

**Propiedades**:
- **Orden**: La primera imagen se usa como imagen principal
- **Tamaño**: Se redimensionan si son >2MB
- **Formato**: Se convierten a WebP para optimizar si es necesario
- **Scope**: Se asocian al organizador (tú controlas esto)
- **Tracking**: Se registra el uso en MediaUsage para saber qué experiencias usan qué imágenes

### Validación

El agente **siempre valida localmente** antes de subir. Si hay errores, te los muestra y no sube nada hasta que se corrijan.

---

## ✅ Checklist antes de procesar

- [ ] Carpeta creada en `carga/<tipo>/<nombre>/`
- [ ] Al menos un archivo de descripción (`.txt`, `.md`, o `.json`)
- [ ] Al menos una imagen (recomendado 3-5)
- [ ] Sabes el nombre del organizador o su UUID
- [ ] Los archivos no contienen información sensible (contraseñas, tokens)

---

## 🤝 Ayuda

Si algo no funciona:
1. **Revisa los logs**: El agente muestra qué archivos procesó y qué errores encontró
2. **Valida el JSON**: El agente puede ejecutar `validate_payload.py` manualmente
3. **Consulta la documentación**: `docs/PLATAFORMA_CONTENIDO.md` tiene todos los campos
4. **Prueba con la plantilla**: Copia `_plantilla.json` y complétala manualmente

---

**Última actualización**: 2026-02-10  
**Mantenido por**: Sistema IA de carga de contenido
