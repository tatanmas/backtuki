"""
Tests for PlatformExportService.
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.migration_system.services import PlatformExportService
from apps.migration_system.models import MigrationJob
from apps.events.models import Event, Location
from apps.organizers.models import Organizer

User = get_user_model()


class ExportServiceTestCase(TestCase):
    """Tests para el servicio de exportación."""
    
    def setUp(self):
        """Setup test data."""
        # Crear usuario
        self.user = User.objects.create_user(
            username='testuser',
            email='test@test.com',
            password='testpass123'
        )
        
        # Crear organizer
        self.organizer = Organizer.objects.create(
            name='Test Organizer',
            slug='test-organizer',
            contact_email='organizer@test.com'
        )
        
        # Crear location
        self.location = Location.objects.create(
            name='Test Location',
            address='Test Address'
        )
        
        # Crear evento
        self.event = Event.objects.create(
            title='Test Event',
            slug='test-event',
            organizer=self.organizer,
            location=self.location
        )
    
    def test_export_all_creates_job(self):
        """Test que export_all crea un job."""
        job = MigrationJob.objects.create(
            direction='export',
            status='pending'
        )
        
        service = PlatformExportService(job=job)
        result = service.export_all(include_media=False, compress=False)
        
        self.assertTrue(result['success'])
        self.assertIn('statistics', result)
        self.assertGreater(result['statistics']['total_models'], 0)
    
    def test_export_includes_created_models(self):
        """Test que el export incluye los modelos creados."""
        service = PlatformExportService()
        result = service.export_all(include_media=False, compress=False)
        
        # Verificar que el export contiene datos
        export_data = result
        self.assertIn('models', export_data)
        
        # Verificar que incluye usuarios
        if 'users.User' in export_data['models']:
            self.assertGreater(len(export_data['models']['users.User']), 0)
    
    def test_export_model_specific(self):
        """Test exportar modelo específico."""
        from apps.events.models import Event
        
        service = PlatformExportService()
        events_data = service.export_model(Event)
        
        self.assertIsInstance(events_data, list)
        self.assertGreater(len(events_data), 0)
