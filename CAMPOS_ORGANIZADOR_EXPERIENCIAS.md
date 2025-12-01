# 📋 Campos Necesarios para Organizador con Experiencias

## ⚠️ Campos CRÍTICOS (Obligatorios)

### Tabla: `organizers_organizer`

| Campo | Tipo | Valor | Descripción |
|-------|------|-------|-------------|
| `has_experience_module` | Boolean | `TRUE` | **CRÍTICO**: Activa el módulo de experiencias |
| `experience_dashboard_template` | Char(20) | `'free_tours'` o `'standard'` | Template del dashboard |
| `status` | Char(20) | `'active'` | Estado del organizador |
| `name` | Char(255) | Cualquier nombre | Nombre del organizador |
| `slug` | SlugField | Único | Slug único del organizador |
| `contact_email` | EmailField | Email válido | Email de contacto |

### Tabla: `organizers_organizeruser`

| Campo | Tipo | Valor | Descripción |
|-------|------|-------|-------------|
| `can_manage_experiences` | Boolean | `TRUE` | **CRÍTICO**: Permite gestionar experiencias |
| `organizer_id` | UUID | UUID del organizador | Relación con organizador |
| `user_id` | Integer | ID del usuario | Relación con usuario |

## ✅ Campos Recomendados

| Campo | Valor Recomendado |
|-------|------------------|
| `onboarding_completed` | `TRUE` |
| `email_validated` | `TRUE` |
| `is_temporary` | `FALSE` |

## 🚀 SQL Rápido (Actualizar Organizador Existente)

```sql
-- 1. Actualizar organizador
UPDATE organizers_organizer
SET 
    has_experience_module = TRUE,
    experience_dashboard_template = 'free_tours',
    status = 'active'
WHERE slug = 'tu-slug-aqui';

-- 2. Actualizar permisos del usuario
UPDATE organizers_organizeruser
SET can_manage_experiences = TRUE
WHERE organizer_id = (SELECT id FROM organizers_organizer WHERE slug = 'tu-slug-aqui');
```

## 🐍 Python Rápido (Django Shell)

```python
from apps.organizers.models import Organizer, OrganizerUser

# Actualizar organizador
org = Organizer.objects.get(slug='tu-slug-aqui')
org.has_experience_module = True
org.experience_dashboard_template = 'free_tours'
org.status = 'active'
org.save()

# Actualizar permisos
OrganizerUser.objects.filter(organizer=org).update(can_manage_experiences=True)
```

## 📝 Valores de `experience_dashboard_template`

- `'standard'` → Dashboard estándar de experiencias
- `'free_tours'` → Dashboard personalizado para Free Tours

## ✅ Checklist de Verificación

- [ ] `has_experience_module = TRUE` en `organizers_organizer`
- [ ] `experience_dashboard_template = 'free_tours'` (o 'standard')
- [ ] `status = 'active'` en `organizers_organizer`
- [ ] `can_manage_experiences = TRUE` en `organizers_organizeruser`
- [ ] Usuario vinculado en `organizers_organizeruser`
- [ ] `onboarding_completed = TRUE` (recomendado)
- [ ] `email_validated = TRUE` (recomendado)

## 🔍 Verificar Configuración

```sql
SELECT 
    o.name,
    o.slug,
    o.has_experience_module,
    o.experience_dashboard_template,
    o.status,
    ou.can_manage_experiences,
    u.email
FROM organizers_organizer o
LEFT JOIN organizers_organizeruser ou ON o.id = ou.organizer_id
LEFT JOIN users_user u ON ou.user_id = u.id
WHERE o.slug = 'tu-slug-aqui';
```

