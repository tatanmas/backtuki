# ExperienceReview model and review_token on ExperienceReservation

import uuid
from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('experiences', '0012_add_attended_at_to_reservation'),
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='experiencereservation',
            name='review_token',
            field=models.UUIDField(
                blank=True,
                editable=False,
                help_text='Token for unique review form link sent to customer after attended',
                null=True,
                unique=True,
                verbose_name='review token',
            ),
        ),
        migrations.CreateModel(
            name='ExperienceReview',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated at')),
                ('rating', models.PositiveSmallIntegerField(help_text='1-5 stars', validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(5)], verbose_name='rating')),
                ('title', models.CharField(blank=True, max_length=255, verbose_name='title')),
                ('body', models.TextField(blank=True, verbose_name='body')),
                ('status', models.CharField(choices=[('draft', 'Draft'), ('pending', 'Pending moderation'), ('approved', 'Approved'), ('rejected', 'Rejected')], db_index=True, default='approved', max_length=20, verbose_name='status')),
                ('experience', models.ForeignKey(on_delete=models.CASCADE, related_name='reviews', to='experiences.experience', verbose_name='experience')),
                ('reservation', models.OneToOneField(help_text='Reservation this review is for (one review per reservation)', on_delete=models.CASCADE, related_name='review', to='experiences.experiencereservation', verbose_name='reservation')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name='experience_reviews', to='users.user', verbose_name='user')),
            ],
            options={
                'verbose_name': 'experience review',
                'verbose_name_plural': 'experience reviews',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='experiencereview',
            constraint=models.UniqueConstraint(fields=('reservation',), name='unique_review_per_reservation'),
        ),
    ]
