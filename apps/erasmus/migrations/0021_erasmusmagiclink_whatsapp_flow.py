"""
Migration 0021 – Rework ErasmusMagicLink for the two-phase WhatsApp flow.

Changes to ErasmusMagicLink:
  - Add `verification_code`  (replaces the pre-generated access_token concept for Phase 1)
  - Make `access_token` nullable (set only after WhatsApp message is received)
  - Add `status` CharField  (pending_whatsapp | link_sent | used | expired)
  - Add `link_expires_at`   (expiry for access_token, separate from verification code expiry)
  - Remove `is_used` BooleanField (replaced by status)
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("erasmus", "0020_erasmuslocalpartner_erasmusmagiclink"),
    ]

    operations = [
        # 1. Add verification_code with unique=True (table is new, no existing rows)
        migrations.AddField(
            model_name="erasmusmagiclink",
            name="verification_code",
            field=models.CharField(
                verbose_name="verification code",
                max_length=30,
                null=True,
                blank=True,
                unique=True,
                db_index=True,
                help_text="Code embedded in the WhatsApp pre-fill message (e.g. ERAS-A1B2C3)",
            ),
        ),
        # 2. Make existing access_token nullable
        migrations.AlterField(
            model_name="erasmusmagiclink",
            name="access_token",
            field=models.CharField(
                verbose_name="access token",
                max_length=64,
                null=True,
                blank=True,
                db_index=True,
                help_text="Secure random token set when WhatsApp message is received",
            ),
        ),
        # 3. Add status field
        migrations.AddField(
            model_name="erasmusmagiclink",
            name="status",
            field=models.CharField(
                verbose_name="status",
                max_length=25,
                choices=[
                    ("pending_whatsapp", "Waiting for WhatsApp message"),
                    ("link_sent", "Magic link sent via WhatsApp"),
                    ("used", "Used – student logged in"),
                    ("expired", "Expired"),
                ],
                default="pending_whatsapp",
                db_index=True,
            ),
        ),
        # 4. Add link_expires_at
        migrations.AddField(
            model_name="erasmusmagiclink",
            name="link_expires_at",
            field=models.DateTimeField(
                verbose_name="link expires at",
                null=True,
                blank=True,
            ),
        ),
        # 5. Remove is_used (superseded by status)
        migrations.RemoveField(
            model_name="erasmusmagiclink",
            name="is_used",
        ),
    ]
