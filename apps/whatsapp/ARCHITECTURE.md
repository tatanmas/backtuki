# Arquitectura de Integración WhatsApp

## Visión General

Este documento describe la arquitectura del sistema de integración WhatsApp, que conecta Django (backend) con un servicio Node.js que utiliza `whatsapp-web.js` para interactuar con WhatsApp Web.

## Componentes Principales

### 1. Servicio Node.js (`whatsapp-service/`)

**Responsabilidades:**
- Mantener conexión con WhatsApp Web usando `whatsapp-web.js`
- Generar y exponer códigos QR para autenticación
- Capturar mensajes entrantes y salientes
- Enviar mensajes a través de WhatsApp
- Proporcionar información de chats y grupos

**Estructura:**
```
whatsapp-service/
├── src/
│   ├── config/          # Configuración global
│   ├── handlers/        # Manejadores de eventos (qr, ready, message)
│   ├── routes/          # Endpoints API (messages, status, chats, groups)
│   ├── services/        # Servicios internos (whatsappClient)
│   └── utils/           # Utilidades (contactHelper, chatHelper)
└── server.js            # Punto de entrada
```

**Comunicación:**
- Escucha en puerto `3001`
- Expone endpoints REST para Django
- Envía webhooks a Django cuando ocurren eventos (mensajes, QR, conexión)

### 2. Backend Django (`backtuki/apps/whatsapp/`)

**Modelos Principales:**

- **WhatsAppSession**: Estado de la sesión de WhatsApp
- **WhatsAppChat**: Chats individuales y grupos
- **WhatsAppMessage**: Mensajes recibidos y enviados
- **TourOperator**: Operadores turísticos que reciben notificaciones
- **ExperienceGroupBinding**: Vinculación entre Experiencias y Grupos de WhatsApp
- **WhatsAppReservationRequest**: Solicitudes de reserva desde WhatsApp

**Servicios (`backtuki/apps/whatsapp/services/`):**

#### `WhatsAppWebService`
Cliente HTTP para comunicarse con el servicio Node.js.

**Métodos principales:**
- `send_message()`: Enviar mensaje
- `get_status()`: Obtener estado de conexión
- `get_qr_code()`: Obtener código QR
- `get_chats()`: Listar todos los chats
- `get_groups()`: Listar grupos
- `get_chat_messages()`: Obtener historial de mensajes

#### `WhatsAppSyncService`
Sincroniza datos del servicio Node.js a la base de datos Django.

**Métodos principales:**
- `sync_all_chats()`: Sincronizar todos los chats
- `sync_all_groups()`: Sincronizar todos los grupos
- `sync_chat()`: Sincronizar un chat específico
- `sync_chat_messages()`: Sincronizar mensajes de un chat

#### `ExperienceOperatorService`
Gestiona la relación entre Experiencias, Operadores y Grupos de WhatsApp.

**Métodos principales:**
- `get_or_create_operator_for_organizer()`: Crear/obtener operador para organizador
- `create_experience_group_binding()`: Vincular experiencia a grupo
- `get_experience_whatsapp_group()`: Obtener grupo asignado a experiencia
- `remove_experience_group_binding()`: Desvincular experiencia de grupo

**Flujo de Auto-creación:**

1. Cuando un `Organizer` crea una `Experience`:
   - Se crea automáticamente un `TourOperator` si no existe
   - Si el operador tiene un `default_whatsapp_group`, se crea un `ExperienceGroupBinding`

2. El binding puede ser:
   - **Default**: Usa el grupo predeterminado del operador (`is_override=False`)
   - **Override**: Grupo personalizado para la experiencia (`is_override=True`)

### 3. API Endpoints

**Webhooks (Node.js → Django):**
- `POST /api/v1/whatsapp/webhook/process-message/`: Procesar mensaje recibido
- `POST /api/v1/whatsapp/webhook/status/`: Actualizar estado de conexión
- `POST /api/v1/whatsapp/webhook/qr/`: Recibir código QR

**SuperAdmin API:**
- `GET /api/v1/superadmin/whatsapp/status/`: Estado del servicio
- `GET /api/v1/superadmin/whatsapp/qr/`: Código QR actual
- `GET /api/v1/superadmin/whatsapp/chats/`: Listar chats
- `GET /api/v1/superadmin/whatsapp/groups/`: Listar grupos
- `GET /api/v1/superadmin/whatsapp/experiences/`: Listar experiencias con grupos
- `PATCH /api/v1/superadmin/whatsapp/experiences/{id}/group/`: Vincular/desvincular grupo
- `GET /api/v1/superadmin/whatsapp/operators/`: Listar operadores
- `PATCH /api/v1/superadmin/whatsapp/operators/{id}/default-group/`: Establecer grupo predeterminado

## Flujo de Datos

### Mensaje Entrante

```
WhatsApp Web → Node.js Service → Webhook → Django
                                      ↓
                              process_message()
                                      ↓
                              Guardar en DB
                                      ↓
                              Detectar código RES-XXX
                                      ↓
                              Crear WhatsAppReservationRequest
                                      ↓
                              Notificar operador
```

### Mensaje Saliente

```
Django → WhatsAppWebService → Node.js Service → WhatsApp Web
```

### Sincronización de Chats

```
Frontend → Django API → WhatsAppSyncService → Node.js Service
                                                    ↓
                                            Obtener chats
                                                    ↓
                                            Sincronizar a DB
                                                    ↓
                                            Retornar a Frontend
```

## Gestión de Experiencias y Grupos

### Jerarquía de Prioridad

1. **Binding personalizado** (`is_override=True`): Grupo específico para la experiencia
2. **Grupo predeterminado del operador**: Si la experiencia tiene un operador con grupo predeterminado
3. **Binding default** (`is_override=False`): Binding legacy sin override
4. **Sin grupo**: La experiencia no tiene grupo asignado

### Auto-creación de Operadores

Cuando un `Organizer` crea su primera `Experience`:
1. Se crea automáticamente un `TourOperator` vinculado al organizador
2. El operador se marca como `is_system_created=True`
3. Si el operador tiene un `default_whatsapp_group`, se crea un `ExperienceGroupBinding`

## Manejo de Errores

### Robustez

- Todos los servicios incluyen manejo de excepciones
- Los webhooks son idempotentes (verifican duplicados por `whatsapp_id`)
- Los servicios retornan valores por defecto en caso de error
- Logging detallado para debugging

### Timeouts

- `WhatsAppWebService`: Timeout de 10s para operaciones normales
- `get_chat_messages()`: Timeout de 60s para historiales grandes
- `get_chats()`: Timeout de 30s para listar todos los chats

## Seguridad

### Autenticación

- Actualmente los endpoints usan `AllowAny` (TODO: implementar autenticación)
- Los webhooks deberían validar signatures en producción

### Validación

- Validación de tipos de chat (individual vs group)
- Verificación de existencia de grupos antes de vincular
- Validación de datos de entrada en todos los endpoints

## Docker

### Servicios

- **backend**: Django (puerto 8000)
- **whatsapp-service**: Node.js (puerto 3001)

### Red

Ambos servicios están en la misma red Docker (`backtuki_default`), permitiendo comunicación interna usando nombres de servicio:
- Django → Node.js: `http://tuki-whatsapp-service:3001`
- Node.js → Django: `http://backend:8000`

## Comandos de Gestión

### Sincronización

```bash
# Sincronizar todos los chats
python manage.py sync_whatsapp_chats

# Sincronizar mensajes de un chat específico
python manage.py sync_whatsapp_messages <chat_id>

# Migrar operadores a organizadores
python manage.py migrate_operators_to_organizers
```

## Próximas Mejoras

1. **Autenticación**: Implementar autenticación real en endpoints
2. **Validación de Webhooks**: Agregar validación de signatures
3. **Rate Limiting**: Implementar límites de tasa para prevenir abuso
4. **Caché**: Agregar caché para datos frecuentemente accedidos
5. **Métricas**: Implementar métricas y monitoreo
6. **Tests**: Agregar tests comprehensivos para todos los servicios

