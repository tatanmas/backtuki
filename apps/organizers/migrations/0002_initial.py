# Generated by Django 4.2.8 on 2025-04-30 20:07

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('organizers', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='organizeruser',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='organizer_roles', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='organizersubscription',
            name='organizer',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='subscriptions', to='organizers.organizer'),
        ),
        migrations.AddField(
            model_name='domain',
            name='tenant',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='domains', to='organizers.organizer'),
        ),
        migrations.AlterUniqueTogether(
            name='organizeruser',
            unique_together={('user', 'organizer')},
        ),
    ]
