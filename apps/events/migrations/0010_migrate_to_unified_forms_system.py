# Generated manually for enterprise migration to unified forms system
# This migration safely transitions from EventForm to forms.Form

from django.db import migrations, models
import django.db.models.deletion


def clear_existing_form_references(apps, schema_editor):
    """Clear any existing form references to avoid UUID/BigInt conflicts."""
    TicketTier = apps.get_model('events', 'TicketTier')
    # Set all form references to NULL before changing the field type
    TicketTier.objects.update(form=None)


def reverse_clear_form_references(apps, schema_editor):
    """No reverse action needed for clearing references."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('forms', '0001_initial'),
        ('events', '0009_remove_coupon_tenant_id_remove_event_tenant_id_and_more'),
    ]

    operations = [
        # Step 1: Clear existing form references to avoid type conflicts
        migrations.RunPython(
            clear_existing_form_references,
            reverse_clear_form_references,
        ),
        
        # Step 2: Remove the FormField.form relationship first
        migrations.RemoveField(
            model_name='formfield',
            name='form',
        ),
        
        # Step 3: Remove the old form field from TicketTier
        migrations.RemoveField(
            model_name='tickettier',
            name='form',
        ),
        
        # Step 4: Add the new form field pointing to forms.Form
        migrations.AddField(
            model_name='tickettier',
            name='form',
            field=models.ForeignKey(
                blank=True, 
                null=True, 
                on_delete=django.db.models.deletion.SET_NULL, 
                related_name='ticket_tiers', 
                to='forms.form', 
                verbose_name='form'
            ),
        ),
        
        # Step 5: Delete the legacy models
        migrations.DeleteModel(
            name='EventForm',
        ),
        migrations.DeleteModel(
            name='FormField',
        ),
    ] 