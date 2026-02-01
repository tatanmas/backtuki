# 🚀 Tuki Backend - Scripts de Deploy

## 📋 Scripts Disponibles

### 1. `deploy.sh` - Deploy Optimizado (DEFAULT)

**Uso:** Operación normal con 1-100 usuarios simultáneos.

```bash
./deploy.sh
```

**Configuración:**
- Backend: `min-instances=1` (webhooks WhatsApp 24/7)
- Celery Beat: `min-instances=1` (programador de tareas)
- Celery Worker: `min-instances=1` (ejecutor de tareas periódicas)
- Otros workers: `min-instances=0` (escalan cuando necesario)

**Costo estimado:** $27-35k CLP/mes

---

### 2. `deploy-event-mode.sh` - Pre-escalado para Eventos Grandes

**Uso:** Eventos con 1000+ usuarios simultáneos.

```bash
./deploy-event-mode.sh  # Ejecutar 24-48h ANTES del evento
```

**Configuración:**
- Backend: `min-instances=3`
- Workers: `min-instances=2-3` por servicio

**Costo estimado:** $50-70k CLP/mes (solo durante el evento)

**IMPORTANTE:** Después del evento, ejecutar `./deploy.sh` para volver a configuración optimizada.

---

## 🎯 Flujo de Trabajo

### Operación Normal

```bash
# Deploy normal (usa configuración optimizada)
cd backtuki
./deploy.sh
```

### Evento Grande

```bash
# 24-48h ANTES del evento
cd backtuki
./deploy-event-mode.sh

# Esperar evento...

# DESPUÉS del evento (volver a configuración optimizada)
cd backtuki
./deploy.sh
```

---

## 💰 Comparación de Costos

| Escenario | Configuración | Costo/mes |
|-----------|---------------|-----------|
| **Normal** | `deploy.sh` | $27-35k |
| **Evento Grande** | `deploy-event-mode.sh` | $50-70k |
| **Anterior (sin optimizar)** | N/A | $57-69k |

---

## ⚠️ Consideraciones Importantes

### ¿Por qué Backend min=1?

**WhatsApp webhooks requieren disponibilidad 24/7.**

- Si `min=0`, los webhooks tendrían cold start de 5-15 segundos
- Con `min=1`, latencia garantizada <500ms

### ¿Por qué Worker min=1?

**Cloud Run NO escala automáticamente por cola Redis.**

- Celery Beat programa tareas en Redis
- Se necesita al menos 1 worker escuchando para ejecutar tareas periódicas:
  - `cleanup_expired_ticket_holds` (cada 5 min) - evita overselling
  - `ensure_pending_emails_sent` (cada 5 min) - fallback emails
  - `run_scheduled_woocommerce_syncs` (cada 15 min)

### ¿Qué pasa con los otros workers?

**Escalan automáticamente solo cuando hay trabajo.**

- `worker-emails`: Escala cuando hay emails en cola
- `worker-sync`: Escala cuando hay sincronización WooCommerce
- `worker-general`: Escala cuando hay tareas generales
- Si no hay trabajo, costo = $0

---

## 📊 Monitoreo

### Verificar Configuración Actual

```bash
gcloud run services list --platform=managed --region=us-central1 \
  --format="table(name,spec.template.metadata.annotations['autoscaling.knative.dev/minScale'])"
```

### Verificar Webhooks WhatsApp

```bash
gcloud logging read \
  "resource.type=cloud_run_revision AND resource.labels.service_name=tuki-backend AND textPayload:(whatsapp OR webhook)" \
  --project=tukiprod --limit=50
```

### Verificar Tareas Periódicas

```bash
# Celery Beat (programador)
gcloud logging read \
  "resource.type=cloud_run_revision AND resource.labels.service_name=tuki-celery-beat" \
  --project=tukiprod --limit=50

# Cleanup Holds (ejecuta cada 5 min)
gcloud logging read \
  "resource.type=cloud_run_revision AND resource.labels.service_name=tuki-celery-worker AND textPayload:cleanup_expired_ticket_holds" \
  --project=tukiprod --limit=20
```

---

## 📚 Documentación Adicional

- **`/CONFIGURACION_COSTOS_OPTIMIZADA.md`**: Guía completa, FAQ, y detalles técnicos
- **`/IMPLEMENTACION_COMPLETADA.md`**: Resumen de implementación y checklist

---

## 🆘 Troubleshooting

### Webhooks WhatsApp no llegan

```bash
# Verificar que backend tenga min=1
gcloud run services describe tuki-backend --region=us-central1 \
  --format="value(spec.template.metadata.annotations['autoscaling.knative.dev/minScale'])"

# Debe retornar: 1
```

### Tareas periódicas no se ejecutan

```bash
# Verificar que worker tenga min=1
gcloud run services describe tuki-celery-worker --region=us-central1 \
  --format="value(spec.template.metadata.annotations['autoscaling.knative.dev/minScale'])"

# Debe retornar: 1
```

### Costos siguen altos

1. Ejecutar `./deploy.sh` de nuevo
2. Verificar workers especializados en min=0
3. Considerar Phase 1B (Cloud SQL ZONAL) para ahorro adicional

---

**Última actualización:** 18 enero 2026

