# 📋 PASOS PARA CLONAR TUKI DESDE GCP - ENTERPRISE EDITION

## 🏢 VERSIÓN ENTERPRISE

Esta es la versión robusta con logging, verificaciones, rollback automático y manejo de errores completo.

---

## ✅ Paso 1: Instalar gcloud CLI (COMPLETADO)

**Estado:** ✅ gcloud CLI ya está instalado en el servidor  
**Versión:** 552.0.0

---

## 🔐 Paso 2: Configurar credenciales

**Script Recomendado:** `./paso2-service-account.sh` ⭐

### ⚠️ IMPORTANTE: NO necesitas navegador en el servidor

Este método usa **Service Account Key JSON**, que es la forma estándar y segura de autenticar servidores sin interfaz gráfica.

**Cómo funciona:**
1. 🔐 **En tu Mac (con navegador):** El script se autentica usando `gcloud auth login` (abre tu navegador)
2. 🏗️ **En tu Mac:** Crea un Service Account en GCP con permisos mínimos necesarios
3. 📥 **En tu Mac:** Descarga la clave JSON del Service Account
4. 📤 **De tu Mac al servidor:** Transfiere la clave JSON via SCP
5. ⚙️ **En el servidor (sin navegador):** Configura gcloud para usar la clave JSON
6. ✅ **En el servidor:** Verifica que puede acceder a Cloud SQL y Storage

**Una vez configurado, el servidor accede a GCP automáticamente sin intervención manual.**

**Ejecuta:**
```bash
cd /Users/sebamasretamal/Desktop/cursor/tukifull/backtuki/migrador
./paso2-service-account.sh
```

**Qué hace el script:**
1. ✅ Verifica que estás autenticado en tu Mac
2. ✅ Verifica permisos del usuario en Mac
3. ✅ Crea o usa Service Account existente
4. ✅ Asigna roles mínimos necesarios:
   - `roles/cloudsql.client` - Acceso a Cloud SQL
   - `roles/storage.objectViewer` - Leer desde Cloud Storage
   - `roles/storage.objectCreator` - Escribir backups
5. ✅ Descarga key JSON a tu Mac (con permisos 600)
6. ✅ Sube key JSON al servidor
7. ✅ Configura gcloud en el servidor con `activate-service-account`
8. ✅ Verifica acceso a Cloud SQL y Storage

**Qué necesitas:**
- ✅ gcloud CLI instalado en tu Mac
- ✅ Autenticado en tu Mac (`gcloud auth login`)
- ✅ Permisos en GCP para crear Service Accounts (roles/iam.serviceAccountAdmin o roles/owner)
- ✅ Conexión SSH al servidor

**Alternativas (no recomendadas):**
- `./paso2-login-simple.sh` - Login interactivo con `--no-launch-browser` (requiere copiar URL y código)
- `./paso2-login-gcloud-enterprise.sh` - Versión enterprise del login interactivo

**Diagrama de flujo:**
```
┌─────────────┐         ┌─────────────┐         ┌──────────────┐
│ Tu Mac      │         │ GCP         │         │ Servidor     │
│ (navegador) │         │             │         │ (SSH only)   │
└─────────────┘         └─────────────┘         └──────────────┘
       │                       │                        │
       │ 1. auth login         │                        │
       ├──────────────────────>│                        │
       │                       │                        │
       │ 2. create SA          │                        │
       ├──────────────────────>│                        │
       │                       │                        │
       │ 3. download JSON      │                        │
       │<──────────────────────┤                        │
       │                       │                        │
       │ 4. transfer JSON      │                        │
       ├───────────────────────────────────────────────>│
       │                       │                        │
       │                       │ 5. activate SA        │
       │                       │<───────────────────────┤
       │                       │                        │
       │                       │ 6. access resources   │
       │                       │<───────────────────────┤
       │                       │                        │
```

**Características Enterprise:**
- ✅ Verificación de permisos antes de crear Service Account
- ✅ Manejo robusto de errores con mensajes claros
- ✅ Opción de usar, recrear o actualizar Service Account existente
- ✅ Verificación post-configuración de acceso a recursos
- ✅ Permisos de archivo seguros (chmod 600)
- ✅ Instrucciones de seguridad y rotación de claves

**Tiempo estimado:** 2-5 minutos

**Seguridad:**
- 🔒 La clave JSON se protege con `chmod 600` automáticamente
- 🔒 Los roles asignados siguen el principio de menor privilegio
- 🔒 La clave NO se sube a Git (verifica `.gitignore`)
- 🔒 Rotación recomendada cada 90 días

---

## ✅ Paso 3: Verificar acceso a GCP

**Script:** `./paso3-verificar-acceso.sh`

**Ejecuta:**
```bash
./paso3-verificar-acceso.sh
```

**Qué verifica:**
- ✅ Conexión SSH
- ✅ gcloud CLI instalado
- ✅ Autenticación activa
- ✅ Acceso a Cloud SQL
- ✅ Acceso a Cloud Storage
- ✅ Recursos del servidor (disco, memoria)
- ✅ Docker y Docker Compose

**Características Enterprise:**
- ✅ Verificaciones exhaustivas
- ✅ Información detallada de recursos
- ✅ Validación de permisos

**Tiempo estimado:** 1-2 minutos

---

## 🚀 Paso 4: Clonar todo desde GCP

**Script:** `./clone-from-gcp-enterprise.sh` ⭐ **SCRIPT PRINCIPAL**

**Ejecuta:**
```bash
./clone-from-gcp-enterprise.sh
```

**Qué hace:**
1. ✅ **Verificaciones previas completas**
2. ✅ **Detiene tatanfoto_backend** (puerto 8000)
3. ✅ **Crea estructura** en `/home/tatan/Escritorio/tuki-platform`
4. ✅ **Clona base de datos** desde Cloud SQL → PostgreSQL local
5. ✅ **Clona archivos media** desde GCS → filesystem local
6. ✅ **Transfiere código** desde tu Mac → servidor
7. ✅ **Construye imágenes Docker**
8. ✅ **Levanta servicios** (backend, db, redis, celery)
9. ✅ **Restaura base de datos**
10. ✅ **Ejecuta migraciones Django**
11. ✅ **Verificación final completa**

**Características Enterprise:**
- ✅ **Rollback automático** si algo falla
- ✅ **Logging detallado** en `logs/`
- ✅ **Puntos de backup** antes de cambios críticos
- ✅ **Verificaciones en cada paso**
- ✅ **Manejo de errores robusto**
- ✅ **Timeouts configurables**
- ✅ **Verificación de salud de servicios**

**Tiempo estimado:** 30-60 minutos

**Logs generados:**
- `logs/migration-YYYYMMDD-HHMMSS.log` - Log completo
- `logs/errors-YYYYMMDD-HHMMSS.log` - Solo errores

---

## 📊 RESUMEN

| Paso | Script | Tiempo | Estado |
|------|--------|--------|--------|
| 1 | Instalar gcloud | 2-3 min | ✅ Completado |
| 2 | Login gcloud | 2-5 min | ⏳ Pendiente |
| 3 | Verificar acceso | 1-2 min | ⏳ Pendiente |
| 4 | Clonar todo | 30-60 min | ⏳ Pendiente |

**Total estimado:** 35-70 minutos

---

## 🔍 VERIFICACIÓN POST-MIGRACIÓN

Después de completar todos los pasos:

```bash
ssh -p 2222 tatan@tukitickets.duckdns.org
cd /home/tatan/Escritorio/tuki-platform

# Ver estado de servicios
docker-compose ps

# Ver logs
docker-compose logs -f

# Acceder a admin
# http://tukitickets.duckdns.org:8000/admin/
```

**Credenciales:**
- Usuario: `admin`
- Password: `TukiAdmin2025!`

---

## 📚 DOCUMENTACIÓN

- **README_ENTERPRISE.md** - Documentación completa enterprise
- **lib/common.sh** - Librería común con funciones compartidas
- **logs/** - Logs de todas las migraciones

---

**¿Listo para el Paso 2?** Ejecuta el script y sigue las instrucciones.

