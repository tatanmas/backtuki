"""
URL configuration for migration API.
"""

from django.urls import path
from apps.migration_system import views

app_name = 'migration'

urlpatterns = [
    # Export endpoints
    path('export/', views.start_export, name='start-export'),
    path('export-status/<uuid:job_id>/', views.export_status, name='export-status'),
    path('download-export/<uuid:job_id>/', views.download_export, name='download-export'),
    
    # Import endpoints
    path('receive-import/', views.receive_import, name='receive-import'),
    path('receive-file/', views.receive_file, name='receive-file'),
    
    # Media endpoints
    path('media-list/', views.media_list, name='media-list'),
    path('download-file/', views.download_file, name='download-file'),
    
    # Verification and rollback
    path('verify/', views.verify_integrity, name='verify-integrity'),
    path('rollback/<uuid:job_id>/', views.rollback_migration, name='rollback-migration'),
    
    # Jobs management
    path('jobs/', views.list_jobs, name='list-jobs'),
    path('jobs/<uuid:job_id>/logs/', views.job_logs, name='job-logs'),
    
    # Token management (SuperAdmin only)
    path('tokens/', views.manage_migration_tokens, name='migration-tokens'),
    path('tokens/<uuid:token_id>/', views.revoke_migration_token, name='revoke-migration-token'),
    
    # Backup/Restore endpoints (SuperAdmin only)
    path('upload-backup/', views.upload_backup, name='upload-backup'),
    path('restore-backup/<uuid:job_id>/', views.restore_backup, name='restore-backup'),
    path('restore-status/<uuid:job_id>/', views.restore_status, name='restore-status'),
    path('backup-jobs/', views.list_backup_jobs, name='list-backup-jobs'),
]
