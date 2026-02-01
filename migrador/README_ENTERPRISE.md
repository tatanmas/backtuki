# 🏢 MIGRADOR ENTERPRISE - TUKI PLATFORM

Sistema robusto y enterprise-grade para migrar Tuki desde GCP al servidor local.

## 📁 ESTRUCTURA

```
migrador/
├── lib/
│   └── common.sh                    # Librería común con funciones enterprise
├── logs/                            # Logs de todas las migraciones
├── paso1-instalar-gcloud.sh         # Paso 1: Instalar gcloud CLI
├── paso2-login-gcloud-enterprise.sh # Paso 2: Login gcloud (enterprise)
├── paso3-verificar-acceso.sh        # Paso 3: Verificar acceso
├── clone-from-gcp-enterprise.sh     # ⭐ Script principal de clonación
└── docker-compose.homeserver.yml    # Configuración Docker
```

## 🚀 USO

### Secuencia Completa

```bash
cd /Users/sebamasretamal/Desktop/cursor/tukifull/backtuki/migrador

# Paso 1: Instalar gcloud (ya hecho ✅)
# ./paso1-instalar-gcloud.sh

# Paso 2: Login gcloud
./paso2-login-gcloud-enterprise.sh

# Paso 3: Verificar acceso
./paso3-verificar-acceso.sh

# Paso 4: Clonar todo
./clone-from-gcp-enterprise.sh
```

## ✨ CARACTERÍSTICAS ENTERPRISE

### ✅ Robustez

- **Manejo de errores completo:** Rollback automático si algo falla
- **Logging detallado:** Logs completos en `logs/` con timestamps
- **Verificaciones exhaustivas:** Valida cada paso antes de continuar
- **Puntos de backup:** Crea snapshots del estado antes de cambios importantes

### 🔍 Verificaciones

- Conexión SSH
- Instalación de herramientas (gcloud, Docker, etc.)
- Autenticación GCP
- Acceso a recursos (Cloud SQL, GCS)
- Recursos del servidor (disco, memoria)
- Estado de servicios Docker

### 📊 Logging

Todos los scripts generan logs en:
- `logs/migration-YYYYMMDD-HHMMSS.log` - Log completo
- `logs/errors-YYYYMMDD-HHMMSS.log` - Solo errores

### 🔄 Rollback Automático

Si algo falla, el script:
1. Detiene servicios Tuki iniciados
2. Restaura tatanfoto si fue detenido
3. Mantiene backups para recuperación manual

### ⏱️ Tiempos Estimados

- Paso 1 (gcloud): 2-3 min ✅ (ya hecho)
- Paso 2 (login): 2-5 min (interactivo)
- Paso 3 (verificar): 1-2 min
- Paso 4 (clonar): 30-60 min

**Total: 35-70 minutos**

## 📋 REQUISITOS

- ✅ SSH acceso a servidor (tukitickets.duckdns.org:2222)
- ✅ gcloud CLI instalado (Paso 1)
- ✅ Credenciales GCP configuradas (Paso 2)
- ✅ Docker y Docker Compose instalados
- ✅ 10GB espacio en disco libre
- ✅ 2GB RAM disponible

## 🔍 VERIFICACIÓN POST-MIGRACIÓN

```bash
ssh -p 2222 tatan@tukitickets.duckdns.org
cd /home/tatan/Escritorio/tuki-platform

# Ver estado
docker-compose ps

# Ver logs
docker-compose logs -f

# Acceder a admin
# http://tukitickets.duckdns.org:8000/admin/
```

## 🆘 TROUBLESHOOTING

### Error: Conexión SSH falla
- Verifica que el servidor esté encendido
- Verifica credenciales SSH
- Verifica firewall/router

### Error: gcloud no autentica
- Ejecuta `./paso2-login-gcloud-enterprise.sh` nuevamente
- Verifica que la URL se abrió correctamente
- Asegúrate de usar tecnologia@tuki.cl

### Error: No puede acceder a Cloud SQL
- Verifica permisos de la cuenta en GCP Console
- Asegúrate que el proyecto sea `tukiprod`
- Verifica que la instancia esté RUNNABLE

### Error: Servicios Docker no levantan
- Revisa logs: `docker-compose logs`
- Verifica espacio en disco: `df -h`
- Verifica memoria: `free -h`

### Ver logs detallados
```bash
cd migrador/logs
tail -f migration-*.log
tail -f errors-*.log
```

## 📚 DOCUMENTACIÓN ADICIONAL

- `PASOS.md` - Guía paso a paso simple
- `README.md` - Documentación general
- `lib/common.sh` - Funciones compartidas (para developers)

---

**Versión:** Enterprise 1.0  
**Última actualización:** 19 Enero 2026

