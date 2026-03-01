# Generated manually for Group Outreach feature

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('whatsapp', '0018_rename_whatsapp_car_car_is_act_ix_whatsapp_ca_car_id_05884a_idx_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='GroupOutreachConfig',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('enabled', models.BooleanField(db_index=True, default=False, help_text='When enabled, the system will send first messages to eligible participants.', verbose_name='Enabled')),
                ('message_templates', models.JSONField(blank=True, default=list, help_text='List of message texts. One will be chosen at random per send.', verbose_name='Message templates')),
                ('exclude_numbers', models.JSONField(blank=True, default=list, help_text='Phone numbers to never message (e.g. ["56912345678"]).', verbose_name='Exclude numbers')),
                ('min_delay_seconds', models.PositiveIntegerField(default=120, help_text='Minimum seconds between two sends.', verbose_name='Min delay (seconds)')),
                ('max_delay_seconds', models.PositiveIntegerField(default=300, help_text='Maximum seconds between two sends.', verbose_name='Max delay (seconds)')),
                ('max_per_run', models.PositiveSmallIntegerField(default=1, help_text='Max first messages to send per scheduled run.', verbose_name='Max per run')),
                ('skip_saved_contacts', models.BooleanField(default=True, help_text='Do not send to numbers that are in your phone contacts.', verbose_name='Skip saved contacts')),
                ('last_run_at', models.DateTimeField(blank=True, db_index=True, null=True, verbose_name='Last run at')),
                ('group', models.OneToOneField(limit_choices_to={'type': 'group'}, on_delete=django.db.models.deletion.CASCADE, related_name='outreach_config', to='whatsapp.whatsappchat', verbose_name='Group')),
            ],
            options={
                'verbose_name': 'Group outreach config',
                'verbose_name_plural': 'Group outreach configs',
                'app_label': 'whatsapp',
            },
        ),
        migrations.CreateModel(
            name='GroupOutreachSent',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('participant_id', models.CharField(db_index=True, help_text='WhatsApp participant id (e.g. 569xxx@c.us or xxx@lid).', max_length=100, verbose_name='Participant ID')),
                ('phone_normalized', models.CharField(blank=True, db_index=True, help_text='Digits-only phone for exclude lookups.', max_length=50, verbose_name='Phone normalized')),
                ('message_used', models.TextField(blank=True, help_text='The message text that was sent.', verbose_name='Message used')),
                ('message_index', models.PositiveSmallIntegerField(blank=True, null=True, verbose_name='Message template index')),
                ('sent_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now, verbose_name='Sent at')),
                ('config', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sent_records', to='whatsapp.groupoutreachconfig', verbose_name='Outreach config')),
            ],
            options={
                'verbose_name': 'Group outreach sent',
                'verbose_name_plural': 'Group outreach sent',
                'app_label': 'whatsapp',
            },
        ),
        migrations.AddIndex(
            model_name='groupoutreachsent',
            index=models.Index(fields=['config', 'sent_at'], name='whatsapp_gr_config__b0b0b0_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='groupoutreachsent',
            unique_together={('config', 'participant_id')},
        ),
    ]
