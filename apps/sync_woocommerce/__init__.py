"""
🚀 ENTERPRISE: Módulo de Sincronización WooCommerce

Este módulo maneja la sincronización automática de eventos desde WooCommerce
al backend Django usando tareas asíncronas de Celery.

Características:
- Sincronización programable y bajo demanda
- Manejo robusto de errores sin afectar el sistema principal
- Logging detallado y monitoreo
- API endpoints para gestión
- Dashboard de administración
"""

default_app_config = 'apps.sync_woocommerce.apps.SyncWoocommerceConfig'
