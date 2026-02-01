# 🚀 Configuración Manual de Organizador para Experiencias

Esta guía te muestra cómo configurar manualmente un organizador en la base de datos para que pueda usar el módulo de experiencias, específicamente el template de Free Tours.

## 📋 Campos Necesarios en la Tabla `organizers_organizer`

### Campos Obligatorios para Experiencias:

```sql
-- Campos mínimos requeridos
name = 'Nombre del Organizador'
slug = 'slug-unico-del-organizador'  -- Debe ser único
contact_email = 'email@ejemplo.com'
status = 'active'  -- Debe estar activo

-- Campos para activar módulo de experiencias
has_experience_module = TRUE  -- ⚠️ CRÍTICO: Debe ser TRUE
experience_dashboard_template = 'principal'  -- o 'v0' (legacy)
```

### Campos Opcionales pero Recomendados:

```sql
description = 'Descripción del organizador'
contact_phone = '+56912345678'
address = 'Dirección'
city = 'Ciudad'
country = 'Chile'
onboarding_completed = TRUE
email_validated = TRUE
is_temporary = FALSE
```

## 🔧 Script SQL para Configurar un Organizador Existente

```sql
-- Actualizar un organizador existente para activar experiencias
UPDATE organizers_organizer
SET 
    has_experience_module = TRUE,
    experience_dashboard_template = 'principal',  -- o 'v0' (legacy)
    status = 'active',
    onboarding_completed = TRUE,
    email_validated = TRUE
WHERE 
    slug = 'tu-slug-aqui'  -- Reemplaza con el slug de tu organizador
    -- O usa: id = 'uuid-del-organizador'
    -- O usa: contact_email = 'email@ejemplo.com';
```

## 🆕 Script SQL para Crear un Organizador Nuevo

```sql
-- Insertar un nuevo organizador con módulo de experiencias
INSERT INTO organizers_organizer (
    id,
    name,
    slug,
    contact_email,
    status,
    has_experience_module,
    experience_dashboard_template,
    onboarding_completed,
    email_validated,
    is_temporary,
    created_at,
    updated_at
)
VALUES (
    gen_random_uuid(),  -- PostgreSQL genera UUID automáticamente
    'Free Tours Santiago',
    'free-tours-santiago',  -- Debe ser único
    'contacto@freetours.cl',
    'active',
    TRUE,  -- Activar módulo de experiencias
    'principal',  -- Template Principal
    TRUE,
    TRUE,
    FALSE,
    NOW(),
    NOW()
);
```

## 👤 Vincular Usuario con Organizador

Después de crear/actualizar el organizador, necesitas vincular un usuario:

```sql
-- Verificar si existe OrganizerUser para este usuario
SELECT * FROM organizers_organizeruser 
WHERE user_id = (SELECT id FROM users_user WHERE email = 'usuario@ejemplo.com');

-- Si no existe, crear la relación
INSERT INTO organizers_organizeruser (
    id,
    organizer_id,
    user_id,
    role,
    can_manage_events,
    can_manage_experiences,  -- ⚠️ Importante para experiencias
    can_manage_accommodations,
    created_at,
    updated_at
)
VALUES (
    gen_random_uuid(),
    (SELECT id FROM organizers_organizer WHERE slug = 'free-tours-santiago'),
    (SELECT id FROM users_user WHERE email = 'usuario@ejemplo.com'),
    'admin',
    TRUE,
    TRUE,  -- ⚠️ CRÍTICO: Debe ser TRUE para gestionar experiencias
    FALSE,
    NOW(),
    NOW()
);
```

## 🐍 Script Python (Django Shell)

Alternativamente, puedes usar el shell de Django:

```bash
docker exec -it backtuki-backend-1 python manage.py shell
```

```python
from apps.organizers.models import Organizer, OrganizerUser
from django.contrib.auth import get_user_model

User = get_user_model()

# Opción 1: Actualizar organizador existente
organizer = Organizer.objects.get(slug='tu-slug-aqui')
organizer.has_experience_module = True
organizer.experience_dashboard_template = 'principal'
organizer.status = 'active'
organizer.onboarding_completed = True
organizer.email_validated = True
organizer.save()

# Opción 2: Crear nuevo organizador
organizer = Organizer.objects.create(
    name='Free Tours Santiago',
    slug='free-tours-santiago',
    contact_email='contacto@freetours.cl',
    status='active',
    has_experience_module=True,
    experience_dashboard_template='principal',
    onboarding_completed=True,
    email_validated=True
)

# Vincular usuario con organizador
user = User.objects.get(email='usuario@ejemplo.com')
OrganizerUser.objects.get_or_create(
    organizer=organizer,
    user=user,
    defaults={
        'role': 'admin',
        'can_manage_events': True,
        'can_manage_experiences': True,  # ⚠️ CRÍTICO
        'can_manage_accommodations': False,
    }
)
```

## ✅ Verificación

Para verificar que todo está configurado correctamente:

```sql
-- Verificar organizador
SELECT 
    id,
    name,
    slug,
    has_experience_module,
    experience_dashboard_template,
    status
FROM organizers_organizer
WHERE slug = 'tu-slug-aqui';

-- Verificar relación con usuario
SELECT 
    ou.id,
    u.email,
    o.name as organizer_name,
    ou.can_manage_experiences
FROM organizers_organizeruser ou
JOIN users_user u ON ou.user_id = u.id
JOIN organizers_organizer o ON ou.organizer_id = o.id
WHERE o.slug = 'tu-slug-aqui';
```

## 📝 Valores Posibles para `experience_dashboard_template`

- `'principal'` - Dashboard principal de experiencias (default)
- `'v0'` - Dashboard legacy de experiencias (versión antigua)

## ⚠️ Notas Importantes

1. **`has_experience_module`** debe ser `TRUE` para que el organizador vea el módulo de experiencias
2. **`can_manage_experiences`** en `OrganizerUser` debe ser `TRUE` para que el usuario pueda gestionar experiencias
3. El **`status`** debe ser `'active'` para que el organizador pueda acceder al sistema
4. El **`slug`** debe ser único en toda la base de datos
5. Si el organizador no tiene `email_validated = TRUE`, puede que no pueda acceder a ciertas funcionalidades

## 🔍 Consultas Útiles

```sql
-- Listar todos los organizadores con módulo de experiencias
SELECT name, slug, has_experience_module, experience_dashboard_template
FROM organizers_organizer
WHERE has_experience_module = TRUE;

-- Ver todos los usuarios que pueden gestionar experiencias
SELECT 
    u.email,
    o.name as organizer_name,
    ou.can_manage_experiences
FROM organizers_organizeruser ou
JOIN users_user u ON ou.user_id = u.id
JOIN organizers_organizer o ON ou.organizer_id = o.id
WHERE ou.can_manage_experiences = TRUE;
```

