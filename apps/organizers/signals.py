"""Signals for the organizers app."""

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils.text import slugify
from django.contrib.auth import get_user_model

from .models import Organizer, OrganizerUser, Domain

User = get_user_model()


@receiver(pre_save, sender=Organizer)
def create_organizer_slug(sender, instance, **kwargs):
    """Create a slug for the organizer if not set."""
    if not instance.slug:
        base_slug = slugify(instance.name)
        
        # Check if slug already exists
        counter = 1
        slug = base_slug
        while Organizer.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        
        instance.slug = slug


@receiver(post_save, sender=Organizer)
def create_organizer_domain(sender, instance, created, **kwargs):
    """Create a domain for the organizer if not exists."""
    if created:
        # Create a subdomain based on the slug
        Domain.objects.create(
            domain=f"{instance.slug}.tuki.cl",
            tenant=instance,
            is_primary=True
        )


@receiver(post_save, sender=User)
def create_organizer_for_user(sender, instance, created, **kwargs):
    """Create an organizer for a user when marked as an organizer."""
    if created and instance.is_organizer:
        # Create a new organizer
        organizer = Organizer.objects.create(
            name=f"{instance.get_full_name() or instance.username}'s Organization",
            schema_name=f"org_{instance.id}",
            contact_email=instance.email
        )
        
        # Create the user-organizer relationship
        OrganizerUser.objects.create(
            user=instance,
            organizer=organizer,
            is_admin=True,
            can_manage_events=True,
            can_manage_accommodations=True,
            can_manage_experiences=True,
            can_view_reports=True,
            can_manage_settings=True
        ) 