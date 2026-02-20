# ExperienceImportedReview: reviews imported from Google, GetYourGuide, etc. (no reservation)

import uuid
from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('experiences', '0014_add_managed_operator_slug'),
    ]

    operations = [
        migrations.CreateModel(
            name='ExperienceImportedReview',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated at')),
                ('author_name', models.CharField(max_length=255, verbose_name='author name')),
                ('rating', models.PositiveSmallIntegerField(help_text='1-5 stars', validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(5)], verbose_name='rating')),
                ('body', models.TextField(blank=True, verbose_name='body')),
                ('review_date', models.DateField(blank=True, null=True, verbose_name='review date')),
                ('source', models.CharField(blank=True, max_length=50, verbose_name='source')),
                ('experience', models.ForeignKey(on_delete=models.CASCADE, related_name='imported_reviews', to='experiences.experience', verbose_name='experience')),
            ],
            options={
                'verbose_name': 'imported experience review',
                'verbose_name_plural': 'imported experience reviews',
                'ordering': ['-review_date', '-created_at'],
            },
        ),
    ]
