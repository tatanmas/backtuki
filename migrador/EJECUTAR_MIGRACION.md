# 🚀 CÓMO EJECUTAR LA MIGRACIÓN

## ⚡ Inicio Rápido (1 Comando)

```bash
cd /Users/sebamasretamal/Desktop/cursor/tukifull/backtuki
./full-migration-gcp-to-homeserver.sh
```

✅ Eso es todo. El script hace todo automáticamente.

---

## ⏱️ ¿Cuánto Tarda?

- **Mínimo:** 35 minutos
- **Normal:** 45-50 minutos  
- **Máximo:** 70 minutos

---

## 📋 ¿Qué Hace el Script?

1. ✅ Despliega Tuki en tu servidor (tukitickets.duckdns.org)
2. ✅ Migra la base de datos desde GCP
3. ✅ Sincroniza todos los archivos (fotos, PDFs)
4. ✅ Verifica que todo funciona
5. ✅ Te muestra un resumen completo

---

## 🔍 Después de Ejecutar

### 1. Verificar que funciona

Abrir en navegador:
```
http://tukitickets.duckdns.org:8001/admin/
```

Login:
- Usuario: `admin`
- Password: `TukiAdmin2025!`

### 2. Verificar datos

- ✅ Eventos aparecen
- ✅ Órdenes de compra visibles
- ✅ Imágenes se cargan

### 3. Si todo funciona bien

Apagar GCP para ahorrar:

```bash
gcloud run services update tuki-backend --min-instances=0 --region=us-central1
gcloud run services update tuki-celery-unified --min-instances=0 --region=us-central1
gcloud run services update tuki-celery-beat --min-instances=0 --region=us-central1
```

💰 **Ahorro inmediato:** $40-50k CLP/mes

---

## 🆘 Si Algo Sale Mal

### Ver qué pasó

```bash
ssh -p 2222 tatan@tukitickets.duckdns.org
cd /home/tatan/tuki-platform
docker-compose logs
```

### Reiniciar servicios

```bash
docker-compose restart
```

### Volver a GCP (si es necesario)

```bash
# Reactivar servicios
gcloud run services update tuki-backend --min-instances=1 --region=us-central1
gcloud run services update tuki-celery-unified --min-instances=1 --region=us-central1
gcloud run services update tuki-celery-beat --min-instances=1 --region=us-central1

# Esperar 2 minutos
# Ya está funcionando en GCP otra vez
```

---

## 💡 Tips

- **Mejor momento:** 3-6 AM (menos usuarios)
- **Antes de eventos grandes:** Migrar de vuelta a GCP 24h antes
- **Backups:** Se crean automáticamente cada día a las 3 AM

---

## 📞 Ayuda

Ver documentación completa:
- `PLAN_MIGRACION_HOMESERVER.md` - Plan detallado
- `README_HOMESERVER.md` - Comandos útiles
- `RESUMEN_MIGRACION_HOMESERVER.md` - Resumen visual

---

**¿Listo?**

```bash
cd /Users/sebamasretamal/Desktop/cursor/tukifull/backtuki
./full-migration-gcp-to-homeserver.sh
```

🎉 ¡Buena suerte!

