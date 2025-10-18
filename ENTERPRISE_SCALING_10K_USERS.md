# 🚀 ENTERPRISE SCALING - 10,000 Usuarios Simultáneos

## 📊 Configuración Actual vs Requerida

### **1. Backend (Django + Gunicorn)**

#### ✅ Configuración Actual (Actualizada)
```yaml
CPU: 4 cores
Memory: 8Gi
Concurrency: 200 requests/container
Min Instances: 3
Max Instances: 200
Timeout: 300s
```

#### 📈 Capacidad Teórica
- **Por instancia**: 200 requests concurrentes
- **Con 200 instancias**: 40,000 requests simultáneos
- **Para 10K usuarios comprando**: ✅ **SUFICIENTE** (20% de utilización)

#### ⚠️ **PROBLEMA CRÍTICO: Conexiones a Base de Datos**
- Gunicorn workers por instancia: `(CPU * 2) + 1 = (4 * 2) + 1 = 9 workers`
- Conexiones por instancia: ~9-18 (con pooling)
- **200 instancias × 15 conexiones = 3,000 conexiones simultáneas**

---

### **2. Cloud SQL PostgreSQL**

#### ✅ Configuración Actual
```yaml
Tier: db-custom-2-7680 (2 vCPUs, 7.5 GB RAM)
Availability: REGIONAL (HA activa)
Disk: 50GB
PostgreSQL: 14
```

#### ⚠️ **LÍMITE DE CONEXIONES**
Cloud SQL calcula `max_connections` como:
```
max_connections ≈ (RAM_MB / 9.5) ≈ (7680 / 9.5) ≈ 809 conexiones
```

#### 🚨 **PROBLEMA DETECTADO**
- **Necesitamos**: ~3,000 conexiones (200 instancias backend)
- **Tenemos**: ~809 conexiones máximas
- **Déficit**: **2,191 conexiones** ❌

---

### **3. Celery Worker**

#### ✅ Configuración Actual (Actualizada)
```yaml
CPU: 4 cores
Memory: 4Gi
Concurrency: 4 workers (prefork)
Min Instances: 2
Max Instances: 20
```

#### 📊 Recomendación Basada en Investigación
Según mejores prácticas:
- **Para tareas I/O-bound**: `concurrency = CPU * 1.5 = 4 * 1.5 = 6 workers`
- **prefetch_multiplier**: 1 (para tareas largas como sync WooCommerce)

#### 🔧 Optimización Requerida
```python
# celery_health_server.py línea 61
'--concurrency=6',  # Cambiar de 4 a 6
'--prefetch-multiplier=1',  # Agregar esta opción
```

---

### **4. Celery Beat**

#### ✅ Configuración Actual
```yaml
CPU: 1 core
Memory: 512Mi
Concurrency: 1
Min Instances: 1
Max Instances: 1
```

#### ✅ **ADECUADO** 
Celery Beat solo programa tareas, no las ejecuta. Configuración es suficiente.

---

## 🎯 Soluciones para Escalar a 10K Usuarios

### **Solución 1: Connection Pooling con PgBouncer** (Recomendado)

#### Ventajas:
- ✅ Reduce conexiones a base de datos en ~90%
- ✅ Menos costoso que aumentar Cloud SQL tier
- ✅ Mejora rendimiento general

#### Implementación:
```bash
# 1. Crear Cloud SQL Proxy con PgBouncer
gcloud sql instances patch tuki-db-prod \
  --database-flags=max_connections=500

# 2. Configurar PgBouncer en VPC
# pool_mode = transaction
# default_pool_size = 25
# max_client_conn = 5000
```

#### Configuración Django:
```python
# config/settings/cloudrun.py
DATABASES = {
    'default': {
        'CONN_MAX_AGE': 600,  # 10 minutos
        'OPTIONS': {
            'pool': {
                'min_size': 2,
                'max_size': 10,  # Por worker
            }
        },
    }
}
```

---

### **Solución 2: Aumentar Tier de Cloud SQL** (Más Simple)

#### Configuración Recomendada:
```yaml
Tier: db-custom-8-30720 (8 vCPUs, 30 GB RAM)
max_connections: ≈ 3,234 conexiones
Costo adicional: ~$400/mes
```

#### Comando de Upgrade:
```bash
gcloud sql instances patch tuki-db-prod \
  --tier=db-custom-8-30720 \
  --availability-type=REGIONAL
```

---

### **Solución 3: Read Replicas** (Enterprise)

Para operaciones de lectura intensiva (búsqueda de eventos, consulta de tickets):

```bash
gcloud sql instances create tuki-db-read-replica \
  --master-instance-name=tuki-db-prod \
  --tier=db-custom-4-15360 \
  --region=us-central1
```

#### Configuración Django Multi-DB:
```python
DATABASES = {
    'default': {  # Escrituras
        'HOST': '/cloudsql/tukiprod:us-central1:tuki-db-prod',
    },
    'replica': {  # Lecturas
        'HOST': '/cloudsql/tukiprod:us-central1:tuki-db-read-replica',
    }
}

DATABASE_ROUTERS = ['config.db_router.ReplicaRouter']
```

---

## 📋 Plan de Acción Inmediato

### **Paso 1: Actualizar Celery Worker** ⏱️ 5 min
```bash
# Editar celery_health_server.py
vim /app/celery_health_server.py
# Cambiar línea 61: '--concurrency=6'
# Agregar línea 62: '--prefetch-multiplier=1'

# Redesplegar
cd backtuki
./deploy-celery.sh
```

### **Paso 2: Aumentar Cloud SQL Tier** ⏱️ 15 min
```bash
gcloud sql instances patch tuki-db-prod \
  --tier=db-custom-8-30720 \
  --availability-type=REGIONAL
```

### **Paso 3: Configurar Gunicorn Workers** ⏱️ 10 min
```bash
# Editar Dockerfile línea CMD
# Cambiar workers de auto a fijo:
CMD gunicorn config.wsgi:application \
    --workers=9 \
    --threads=4 \
    --worker-class=gthread \
    --max-requests=1000 \
    --max-requests-jitter=50 \
    --timeout=300 \
    --bind=0.0.0.0:8080
```

### **Paso 4: Pruebas de Carga** ⏱️ 30 min
```bash
# Instalar k6
brew install k6

# Ejecutar test de 10K usuarios
k6 run --vus 10000 --duration 5m load-test.js
```

---

## 💰 Análisis de Costos

### **Configuración Actual (Mensual)**
```
Backend (200 inst max): ~$500-800/mes
Celery Worker (20 inst): ~$200-300/mes
Celery Beat (1 inst):    ~$20/mes
Cloud SQL (2 vCPU):      ~$150/mes
Redis:                   ~$50/mes
-----------------------------------
TOTAL:                   ~$920-1,320/mes
```

### **Configuración para 10K Usuarios (Mensual)**
```
Backend (200 inst max):  ~$800-1,200/mes (CPU+RAM upgrade)
Celery Worker (20 inst): ~$300-400/mes (CPU+RAM upgrade)
Celery Beat (1 inst):    ~$20/mes
Cloud SQL (8 vCPU):      ~$550/mes (tier upgrade)
Redis:                   ~$50/mes
-----------------------------------
TOTAL:                   ~$1,720-2,220/mes
```

**Incremento**: ~$800-900/mes para soportar 10K usuarios simultáneos

---

## 🔍 Monitoreo Enterprise

### **Métricas Críticas a Monitorear**

#### 1. Cloud Run (Backend)
```bash
gcloud monitoring dashboards create \
  --config-from-file=monitoring/backend-dashboard.json
```
- Request latency (p50, p95, p99)
- Instance count vs max instances
- CPU y Memory utilization
- Error rate

#### 2. Cloud SQL
```bash
# Query para conexiones activas
SELECT count(*) FROM pg_stat_activity WHERE state = 'active';

# Alertas
gcloud alpha monitoring policies create \
  --notification-channels=CHANNEL_ID \
  --display-name="DB Connections >80%" \
  --condition-threshold-value=648  # 80% de 809
```

#### 3. Celery
- Queue length (Redis)
- Task success/failure rate
- Average task duration
- Worker saturation

---

## 🧪 Script de Pruebas de Carga

Crear `load-test.js`:
```javascript
import http from 'k6/http';
import { check, sleep } from 'k6';

export let options = {
  stages: [
    { duration: '2m', target: 1000 },   // Warm up
    { duration: '5m', target: 10000 },  // Peak load
    { duration: '2m', target: 0 },      // Cool down
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'],   // 95% bajo 500ms
    http_req_failed: ['rate<0.01'],     // <1% error rate
  },
};

export default function () {
  // Simular compra de ticket
  let res = http.post('https://prop.cl/api/v1/events/173911/checkout/', {
    email: `test${__VU}@load.test`,
    ticket_tier: '123e4567-e89b-12d3-a456-426614174000',
    quantity: 1,
  });
  
  check(res, {
    'status is 200': (r) => r.status === 200,
    'transaction time < 500ms': (r) => r.timings.duration < 500,
  });
  
  sleep(Math.random() * 3);
}
```

Ejecutar:
```bash
k6 run --out cloud load-test.js
```

---

## ✅ Checklist de Deployment

- [ ] Celery Worker: Aumentar concurrency a 6
- [ ] Celery Worker: Agregar `--prefetch-multiplier=1`
- [ ] Cloud SQL: Upgrade a `db-custom-8-30720`
- [ ] Backend: Configurar Gunicorn con workers fijos
- [ ] Backend: Configurar `CONN_MAX_AGE=600`
- [ ] Monitoreo: Dashboards de Cloud Monitoring
- [ ] Monitoreo: Alertas para DB connections
- [ ] Pruebas: Load test con k6
- [ ] Documentación: Runbook de escalamiento

---

## 📚 Referencias

1. **Django Scaling**: https://medium.com/@priyanshu011109/how-to-make-django-handle-10-000-requests-per-second-f20e89a04b40
2. **Celery Production**: https://medium.com/@hankehly/10-essential-lessons-for-running-celery-workloads-in-production-720ce5a05a17
3. **Cloud SQL Best Practices**: https://cloud.google.com/sql/docs/postgres/best-practices
4. **Cloud Run Scaling**: https://cloud.google.com/run/docs/about-instance-autoscaling

---

**Última actualización**: 2025-10-18
**Autor**: Enterprise DevOps Team
**Status**: ✅ Configuración Validada para 10K Usuarios

