#!/usr/bin/env python
"""
Script to create a test tenant organization.
"""

import os
import django
from django.utils import timezone

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.organizers.models import Organizer, Domain
from django.contrib.auth import get_user_model

User = get_user_model()

def create_test_tenant():
    """Create a test tenant and its domain."""
    print("Creating test organization tenant...")
    
    # Create the tenant
    tenant = Organizer.objects.create(
        name="Test Organization",
        slug="test-org",
        schema_name="test_org",
        description="This is a test organization for development",
        contact_email="test@testorg.com",
        has_events_module=True,
        has_accommodation_module=True,
        has_experience_module=True
    )
    
    # Create a domain for the tenant
    domain = Domain.objects.create(
        domain='test.localhost',
        tenant=tenant,
        is_primary=True
    )
    
    print(f"Created tenant: {tenant.name} (schema: {tenant.schema_name})")
    print(f"Created domain: {domain.domain}")
    
    # Create a subscription
    tenant.subscriptions.create(
        plan='premium',
        status='active',
        start_date=timezone.now().date(),
        max_events=100,
        max_accommodations=50,
        max_experiences=50,
        max_storage_gb=10,
        max_users=5
    )
    
    print("Added subscription with Premium plan")
    
    # Link the admin user if it exists
    try:
        admin_user = User.objects.get(email='admin@tuki.cl')
        tenant.organizer_users.create(
            user=admin_user,
            is_admin=True,
            can_manage_events=True,
            can_manage_accommodations=True,
            can_manage_experiences=True,
            can_view_reports=True,
            can_manage_settings=True
        )
        print(f"User {admin_user.email} linked to tenant")
    except User.DoesNotExist:
        print("Admin user not found. Skipping user linking.")
    
    return tenant

if __name__ == "__main__":
    tenant = create_test_tenant()
    print("Done!") 