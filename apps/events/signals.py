"""Signals for the events app."""

from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.utils.text import slugify

from .models import Event, EventCategory


@receiver(pre_save, sender=Event)
def create_event_slug(sender, instance, **kwargs):
    """Create a slug for the event if not set."""
    if not instance.slug:
        base_slug = slugify(instance.title)
        
        # Check if slug already exists
        counter = 1
        slug = base_slug
        while Event.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        
        instance.slug = slug


@receiver(pre_save, sender=EventCategory)
def create_category_slug(sender, instance, **kwargs):
    """Create a slug for the event category if not set."""
    if not instance.slug:
        base_slug = slugify(instance.name)
        
        # Check if slug already exists
        counter = 1
        slug = base_slug
        while EventCategory.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        
        instance.slug = slug 