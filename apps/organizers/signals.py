"""Signals for the organizers app."""

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils.text import slugify
from django.contrib.auth import get_user_model

from .models import Organizer, OrganizerUser

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