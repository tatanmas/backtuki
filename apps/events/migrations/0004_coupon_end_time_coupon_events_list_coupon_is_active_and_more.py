# Generated by Django 4.2.8 on 2025-05-02 08:24

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0003_formfield_conditional_display_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='coupon',
            name='end_time',
            field=models.TimeField(blank=True, null=True, verbose_name='end time'),
        ),
        migrations.AddField(
            model_name='coupon',
            name='events_list',
            field=models.JSONField(blank=True, help_text='List of event IDs this coupon applies to. Null means all events.', null=True, verbose_name='applicable events'),
        ),
        migrations.AddField(
            model_name='coupon',
            name='is_active',
            field=models.BooleanField(default=True, verbose_name='is active'),
        ),
        migrations.AddField(
            model_name='coupon',
            name='start_time',
            field=models.TimeField(blank=True, null=True, verbose_name='start time'),
        ),
        migrations.AlterField(
            model_name='coupon',
            name='event',
            field=models.ForeignKey(blank=True, help_text='Legacy field. If null, coupon applies to all events or specified in events_list', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='coupons', to='events.event', verbose_name='event'),
        ),
    ]
