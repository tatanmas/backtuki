"""
Tests for migration system models.
"""

from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model
from apps.migration_system.models import MigrationJob, MigrationLog, MigrationCheckpoint, MigrationToken

User = get_user_model()


class MigrationJobTestCase(TestCase):
    """Tests para MigrationJob model."""
    
    def setUp(self):
        self.job = MigrationJob.objects.create(
            direction='export',
            status='pending'
        )
    
    def test_start_job(self):
        """Test iniciar job."""
        self.job.start()
        self.assertEqual(self.job.status, 'in_progress')
        self.assertIsNotNone(self.job.started_at)
    
    def test_complete_job(self):
        """Test completar job."""
        self.job.start()
        self.job.complete()
        
        self.assertEqual(self.job.status, 'completed')
        self.assertIsNotNone(self.job.completed_at)
        self.assertEqual(self.job.progress_percent, 100)
    
    def test_fail_job(self):
        """Test marcar job como fallido."""
        self.job.start()
        self.job.fail("Error de prueba")
        
        self.assertEqual(self.job.status, 'failed')
        self.assertEqual(self.job.error_message, "Error de prueba")
    
    def test_update_progress(self):
        """Test actualizar progreso."""
        self.job.update_progress(50, "Exportando datos")
        
        self.assertEqual(self.job.progress_percent, 50)
        self.assertEqual(self.job.current_step, "Exportando datos")


class MigrationTokenTestCase(TestCase):
    """Tests para MigrationToken model."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@test.com',
            password='testpass123'
        )
        
        self.token = MigrationToken.objects.create(
            token=MigrationToken.generate_token(),
            description='Test token',
            permissions='read_write',
            expires_at=timezone.now() + timedelta(hours=24),
            created_by=self.user
        )
    
    def test_token_is_valid(self):
        """Test que token recién creado es válido."""
        self.assertTrue(self.token.is_valid)
    
    def test_token_expires(self):
        """Test que token expirado no es válido."""
        self.token.expires_at = timezone.now() - timedelta(hours=1)
        self.token.save()
        
        self.assertFalse(self.token.is_valid)
    
    def test_mark_used(self):
        """Test marcar token como usado."""
        self.token.mark_used(ip_address='127.0.0.1')
        
        self.assertEqual(self.token.usage_count, 1)
        self.assertEqual(self.token.last_used_ip, '127.0.0.1')
        self.assertIsNotNone(self.token.last_used_at)
    
    def test_single_use_token(self):
        """Test token de un solo uso."""
        self.token.is_single_use = True
        self.token.save()
        
        self.token.mark_used()
        
        self.assertFalse(self.token.is_valid)
    
    def test_revoke_token(self):
        """Test revocar token."""
        self.token.revoke(user=self.user)
        
        self.assertIsNotNone(self.token.revoked_at)
        self.assertEqual(self.token.revoked_by, self.user)
        self.assertFalse(self.token.is_valid)


class MigrationCheckpointTestCase(TestCase):
    """Tests para MigrationCheckpoint model."""
    
    def setUp(self):
        self.checkpoint = MigrationCheckpoint.objects.create(
            name='test-checkpoint',
            description='Test checkpoint',
            snapshot_file_path='/tmp/test.json.gz',
            snapshot_size_mb=1.5,
            total_models=10,
            total_records=1000,
            expires_at=timezone.now() + timedelta(days=30)
        )
    
    def test_checkpoint_is_valid(self):
        """Test que checkpoint recién creado es válido."""
        self.assertTrue(self.checkpoint.is_valid)
        self.assertFalse(self.checkpoint.is_expired)
    
    def test_checkpoint_expires(self):
        """Test que checkpoint expirado se detecta."""
        self.checkpoint.expires_at = timezone.now() - timedelta(days=1)
        self.checkpoint.save()
        
        self.assertTrue(self.checkpoint.is_expired)
    
    def test_mark_as_used(self):
        """Test marcar checkpoint como usado."""
        self.checkpoint.mark_as_used()
        
        self.assertTrue(self.checkpoint.used_for_restore)
        self.assertIsNotNone(self.checkpoint.restored_at)
