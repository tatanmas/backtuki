# ErasmusActivityInscriptionPayment: exclude_from_revenue (cortesía, invitados, prueba)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('erasmus', '0054_alter_erasmusactivityinstanceregistration_created_at_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='erasmusactivityinscriptionpayment',
            name='exclude_from_revenue',
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text='If True, this payment does not count in revenue (cortesía, invited guests, test).',
                verbose_name='exclude from revenue',
            ),
        ),
    ]
