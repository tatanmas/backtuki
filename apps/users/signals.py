"""Signals for the users app."""

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import Group

from .models import User, Profile


@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    """
    Create or update user profile when a User is created or updated.
    """
    if created:
        Profile.objects.create(user=instance)
    else:
        # Update profile if it exists
        if hasattr(instance, 'profile'):
            instance.profile.save()


@receiver(post_save, sender=User)
def assign_user_groups(sender, instance, created, **kwargs):
    """
    Assign appropriate groups to users based on their role.
    """
    if not created:
        return
    
    # Create groups if they don't exist
    organizer_group, _ = Group.objects.get_or_create(name='organizers')
    validator_group, _ = Group.objects.get_or_create(name='ticket_validators')
    client_group, _ = Group.objects.get_or_create(name='clients')
    
    # Assign groups based on user type
    if instance.is_organizer:
        instance.groups.add(organizer_group)
    elif instance.is_validator:
        instance.groups.add(validator_group)
    elif instance.is_client:
        instance.groups.add(client_group) 