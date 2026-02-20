# Generated manually: community directory fields and profile token

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('erasmus', '0016_add_erasmus_registro_background_slide'),
    ]

    operations = [
        migrations.AddField(
            model_name='erasmuslead',
            name='languages_spoken',
            field=models.JSONField(blank=True, default=list, help_text='List of language codes the lead speaks (e.g. es, en, pt)', verbose_name='languages spoken'),
        ),
        migrations.AddField(
            model_name='erasmuslead',
            name='opt_in_community',
            field=models.BooleanField(default=False, help_text='Lead wants to appear in the public community directory', verbose_name='opt in community'),
        ),
        migrations.AddField(
            model_name='erasmuslead',
            name='community_bio',
            field=models.TextField(blank=True, help_text='Optional short description for the community card', verbose_name='community bio'),
        ),
        migrations.AddField(
            model_name='erasmuslead',
            name='profile_photo',
            field=models.ImageField(blank=True, help_text='Optional photo for the community card (uploaded after registration)', null=True, upload_to='erasmus_profiles/%Y/%m/', verbose_name='profile photo'),
        ),
        migrations.AddField(
            model_name='erasmuslead',
            name='community_profile_token',
            field=models.CharField(blank=True, db_index=True, help_text='Token to authorize profile update (photo/bio) from gracias page', max_length=64, null=True, unique=True, verbose_name='community profile token'),
        ),
    ]
