"""
🚀 ENTERPRISE MIGRATION SYSTEM

Sistema robusto de migración backend-a-backend para Tuki Platform.
Permite migrar toda la plataforma (BD + archivos) entre entornos sin scripts externos.

Features:
- Export/Import completo de datos
- Transferencia backend-a-backend
- Verificación de integridad
- Rollback automático
- Progress tracking
- Bidireccional (GCP ↔ Local)
"""

default_app_config = 'apps.migration_system.apps.MigrationSystemConfig'
