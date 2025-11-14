"""Configuración de la app de sincronización WooCommerce"""

from django.apps import AppConfig


class SyncWoocommerceConfig(AppConfig):
    """Configuración de la aplicación de sincronización WooCommerce"""
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.sync_woocommerce'
    verbose_name = '🚀 ENTERPRISE: Sincronización WooCommerce'
    
    def ready(self):
        """Inicialización de la app"""
        # Importar signals si los hay
        try:
            from . import signals
        except ImportError:
            pass
