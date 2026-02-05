# TUKI Creators initial migration

import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('users', '0001_initial'),
        ('experiences', '0009_studentcentertimelineitem_studentinterest_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='CreatorProfile',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated at')),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('slug', models.SlugField(help_text='URL handle for public profile (e.g. /creators/cata/)', max_length=100, unique=True, verbose_name='slug')),
                ('display_name', models.CharField(max_length=255, verbose_name='display name')),
                ('bio', models.TextField(blank=True, verbose_name='bio')),
                ('avatar', models.URLField(blank=True, help_text='Avatar image URL (or use media asset later)', max_length=500, verbose_name='avatar URL')),
                ('location', models.CharField(blank=True, max_length=255, verbose_name='location')),
                ('social_links', models.JSONField(blank=True, default=list, help_text='List of {id, name, url, icon}', verbose_name='social links')),
                ('is_approved', models.BooleanField(default=False, help_text='Whether creator can access dashboard and earn commissions', verbose_name='is approved')),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='creator_profile', to='users.user', verbose_name='user')),
            ],
            options={
                'verbose_name': 'creator profile',
                'verbose_name_plural': 'creator profiles',
                'ordering': ['display_name'],
            },
        ),
        migrations.CreateModel(
            name='CreatorRecommendedExperience',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated at')),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('order', models.PositiveIntegerField(default=0, verbose_name='order')),
                ('creator', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='recommended_experiences', to='creators.creatorprofile', verbose_name='creator')),
                ('experience', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='recommended_by_creators', to='experiences.experience', verbose_name='experience')),
            ],
            options={
                'verbose_name': 'creator recommended experience',
                'verbose_name_plural': 'creator recommended experiences',
                'ordering': ['creator', 'order'],
                'unique_together': {('creator', 'experience')},
            },
        ),
        migrations.AddIndex(
            model_name='creatorprofile',
            index=models.Index(fields=['slug'], name='creators_cr_slug_8b2b0d_idx'),
        ),
        migrations.AddIndex(
            model_name='creatorprofile',
            index=models.Index(fields=['is_approved'], name='creators_cr_is_appr_2c8e0a_idx'),
        ),
        migrations.AddIndex(
            model_name='creatorrecommendedexperience',
            index=models.Index(fields=['creator', 'order'], name='creators_cr_creator_9a1f2b_idx'),
        ),
    ]
