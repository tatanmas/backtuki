"""
Tests for PlatformImportService.
"""

from django.test import TestCase
from apps.migration_system.services import PlatformImportService, PlatformExportService
from apps.migration_system.models import MigrationCheckpoint


class ImportServiceTestCase(TestCase):
    """Tests para el servicio de importación."""
    
    def test_create_checkpoint(self):
        """Test crear checkpoint."""
        service = PlatformImportService()
        checkpoint = service.create_checkpoint(
            name='test-checkpoint',
            description='Test checkpoint'
        )
        
        self.assertIsInstance(checkpoint, MigrationCheckpoint)
        self.assertTrue(checkpoint.is_valid)
        self.assertFalse(checkpoint.is_expired)
    
    def test_validate_export_format(self):
        """Test validar formato de export."""
        service = PlatformImportService()
        
        # Formato válido
        valid_data = {
            'version': '1.0.0',
            'export_date': '2026-01-20T21:00:00Z',
            'models': {},
            'statistics': {}
        }
        
        self.assertTrue(service.validate_export_format(valid_data))
        
        # Formato inválido (falta clave)
        invalid_data = {
            'version': '1.0.0',
            'models': {}
        }
        
        self.assertFalse(service.validate_export_format(invalid_data))
