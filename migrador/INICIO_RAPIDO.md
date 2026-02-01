# ⚡ INICIO RÁPIDO - CLONAR TUKI DESDE GCP

## 🎯 Objetivo

Clonar **TODO** lo que tienes en GCP (base de datos, archivos, código) a tu servidor local en un solo comando.

## 📋 Pasos

### 1. Configurar gcloud CLI en el servidor (solo la primera vez)

```bash
cd /Users/sebamasretamal/Desktop/cursor/tukifull/backtuki/migrador
./setup-gcloud-on-server.sh
```

Este script:
- Instala gcloud CLI si no está
- Te pregunta cómo autenticar (navegador o service account)
- Configura credenciales

**Tiempo:** 5-10 minutos

### 2. Clonar todo desde GCP

```bash
./clone-from-gcp.sh
```

Este script hace **TODO**:
1. ✅ Detiene tatanfoto_backend (libera puerto 8000)
2. ✅ Crea `/home/tatan/Escritorio/tuki-platform`
3. ✅ Clona base de datos desde Cloud SQL
4. ✅ Clona archivos media desde GCS
5. ✅ Transfiere código desde tu Mac
6. ✅ Construye imágenes Docker
7. ✅ Levanta servicios
8. ✅ Restaura base de datos
9. ✅ Ejecuta migraciones Django

**Tiempo:** 30-60 minutos

## ✅ Verificar

Después de ejecutar:

```bash
ssh -p 2222 tatan@tukitickets.duckdns.org
cd /home/tatan/Escritorio/tuki-platform
docker-compose ps
```

Abrir en navegador:
- **Backend:** http://tukitickets.duckdns.org:8000
- **Admin:** http://tukitickets.duckdns.org:8000/admin/
  - Usuario: `admin`
  - Password: `TukiAdmin2025!`

## 🆘 Si algo falla

Ver logs:
```bash
ssh -p 2222 tatan@tukitickets.duckdns.org
cd /home/tatan/Escritorio/tuki-platform
docker-compose logs -f
```

---

**¡Eso es todo!** 🎉

