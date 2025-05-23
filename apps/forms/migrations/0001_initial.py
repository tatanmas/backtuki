# Generated by Django 4.2.8 on 2025-05-03 18:09

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('organizers', '0006_bankingdetails_billingdetails_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='Form',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('status', models.CharField(choices=[('active', 'Active'), ('inactive', 'Inactive'), ('draft', 'Draft')], default='active', max_length=20)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_forms', to=settings.AUTH_USER_MODEL)),
                ('organizer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='form_templates', to='organizers.organizer')),
            ],
            options={
                'ordering': ['-updated_at'],
            },
        ),
        migrations.CreateModel(
            name='FormField',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('label', models.CharField(max_length=255)),
                ('type', models.CharField(choices=[('text', 'Text'), ('email', 'Email'), ('phone', 'Phone'), ('number', 'Number'), ('select', 'Select'), ('checkbox', 'Checkbox'), ('radio', 'Radio'), ('date', 'Date'), ('textarea', 'Textarea'), ('heading', 'Heading'), ('paragraph', 'Paragraph')], max_length=20)),
                ('required', models.BooleanField(default=False)),
                ('placeholder', models.CharField(blank=True, max_length=255, null=True)),
                ('help_text', models.TextField(blank=True, null=True)),
                ('default_value', models.TextField(blank=True, null=True)),
                ('order', models.PositiveIntegerField(default=0)),
                ('width', models.CharField(choices=[('full', 'Full Width'), ('half', 'Half Width'), ('third', 'Third Width')], default='full', max_length=10)),
                ('form', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='fields', to='forms.form')),
            ],
            options={
                'ordering': ['order'],
            },
        ),
        migrations.CreateModel(
            name='FieldValidation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('type', models.CharField(choices=[('required', 'Required'), ('min_length', 'Minimum Length'), ('max_length', 'Maximum Length'), ('min_value', 'Minimum Value'), ('max_value', 'Maximum Value'), ('pattern', 'Pattern/Regex'), ('email', 'Email Format')], max_length=20)),
                ('value', models.CharField(blank=True, max_length=255, null=True)),
                ('message', models.CharField(blank=True, max_length=255, null=True)),
                ('field', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='validations', to='forms.formfield')),
            ],
        ),
        migrations.CreateModel(
            name='FieldOption',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('label', models.CharField(max_length=255)),
                ('value', models.CharField(max_length=255)),
                ('order', models.PositiveIntegerField(default=0)),
                ('field', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='options', to='forms.formfield')),
            ],
            options={
                'ordering': ['order'],
            },
        ),
        migrations.CreateModel(
            name='ConditionalLogic',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('condition', models.CharField(choices=[('equals', 'Equals'), ('not_equals', 'Not Equals'), ('contains', 'Contains'), ('not_contains', 'Not Contains'), ('greater_than', 'Greater Than'), ('less_than', 'Less Than')], max_length=20)),
                ('value', models.CharField(max_length=255)),
                ('field', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='conditional_logic', to='forms.formfield')),
                ('source_field', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='target_logic', to='forms.formfield')),
            ],
        ),
    ]
