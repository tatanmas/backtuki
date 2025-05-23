# Generated by Django 4.2.8 on 2025-05-02 08:07

import apps.events.models
from django.conf import settings
import django.core.validators
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('organizers', '0006_bankingdetails_billingdetails_and_more'),
        ('events', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Coupon',
            fields=[
                ('tenant_id', models.CharField(db_index=True, max_length=50)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated at')),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('code', models.CharField(max_length=50, unique=True, verbose_name='code')),
                ('description', models.TextField(blank=True, verbose_name='description')),
                ('discount_type', models.CharField(choices=[('percentage', 'Percentage'), ('fixed', 'Fixed Amount')], default='percentage', max_length=20, verbose_name='discount type')),
                ('discount_value', models.DecimalField(decimal_places=2, max_digits=10, validators=[django.core.validators.MinValueValidator(0)], verbose_name='discount value')),
                ('min_purchase', models.DecimalField(decimal_places=2, default=0, max_digits=10, validators=[django.core.validators.MinValueValidator(0)], verbose_name='minimum purchase')),
                ('max_discount', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, validators=[django.core.validators.MinValueValidator(0)], verbose_name='maximum discount')),
                ('start_date', models.DateTimeField(blank=True, null=True, verbose_name='start date')),
                ('end_date', models.DateTimeField(blank=True, null=True, verbose_name='end date')),
                ('usage_limit', models.PositiveIntegerField(blank=True, null=True, verbose_name='usage limit')),
                ('usage_count', models.PositiveIntegerField(default=0, verbose_name='usage count')),
                ('status', models.CharField(choices=[('active', 'Active'), ('expired', 'Expired'), ('used', 'Used'), ('inactive', 'Inactive')], default='active', max_length=20, verbose_name='status')),
            ],
            options={
                'verbose_name': 'coupon',
                'verbose_name_plural': 'coupons',
            },
        ),
        migrations.CreateModel(
            name='EventForm',
            fields=[
                ('tenant_id', models.CharField(db_index=True, max_length=50)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated at')),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=100, verbose_name='name')),
                ('description', models.TextField(blank=True, verbose_name='description')),
                ('is_default', models.BooleanField(default=False, verbose_name='is default')),
                ('organizer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='forms', to='organizers.organizer', verbose_name='organizer')),
            ],
            options={
                'verbose_name': 'event form',
                'verbose_name_plural': 'event forms',
            },
        ),
        migrations.CreateModel(
            name='Order',
            fields=[
                ('tenant_id', models.CharField(db_index=True, max_length=50)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated at')),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('order_number', models.CharField(default=apps.events.models.generate_order_number, max_length=50, unique=True, verbose_name='order number')),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('paid', 'Paid'), ('cancelled', 'Cancelled'), ('refunded', 'Refunded'), ('failed', 'Failed')], default='pending', max_length=20, verbose_name='status')),
                ('email', models.EmailField(max_length=254, verbose_name='email')),
                ('first_name', models.CharField(max_length=100, verbose_name='first name')),
                ('last_name', models.CharField(max_length=100, verbose_name='last name')),
                ('phone', models.CharField(blank=True, max_length=20, verbose_name='phone')),
                ('subtotal', models.DecimalField(decimal_places=2, max_digits=10, validators=[django.core.validators.MinValueValidator(0)], verbose_name='subtotal')),
                ('taxes', models.DecimalField(decimal_places=2, default=0, max_digits=10, validators=[django.core.validators.MinValueValidator(0)], verbose_name='taxes')),
                ('service_fee', models.DecimalField(decimal_places=2, default=0, max_digits=10, validators=[django.core.validators.MinValueValidator(0)], verbose_name='service fee')),
                ('total', models.DecimalField(decimal_places=2, max_digits=10, validators=[django.core.validators.MinValueValidator(0)], verbose_name='total')),
                ('currency', models.CharField(default='CLP', max_length=3, verbose_name='currency')),
                ('payment_method', models.CharField(blank=True, max_length=50, verbose_name='payment method')),
                ('payment_id', models.CharField(blank=True, max_length=100, verbose_name='payment id')),
                ('discount', models.DecimalField(decimal_places=2, default=0, max_digits=10, validators=[django.core.validators.MinValueValidator(0)], verbose_name='discount')),
                ('notes', models.TextField(blank=True, verbose_name='notes')),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True, verbose_name='IP address')),
                ('user_agent', models.TextField(blank=True, verbose_name='user agent')),
                ('refund_reason', models.TextField(blank=True, verbose_name='refund reason')),
                ('refunded_amount', models.DecimalField(decimal_places=2, default=0, max_digits=10, validators=[django.core.validators.MinValueValidator(0)], verbose_name='refunded amount')),
                ('coupon', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='orders', to='events.coupon', verbose_name='coupon')),
            ],
            options={
                'verbose_name': 'order',
                'verbose_name_plural': 'orders',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='OrderItem',
            fields=[
                ('tenant_id', models.CharField(db_index=True, max_length=50)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated at')),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('quantity', models.PositiveIntegerField(verbose_name='quantity')),
                ('unit_price', models.DecimalField(decimal_places=2, max_digits=10, validators=[django.core.validators.MinValueValidator(0)], verbose_name='unit price')),
                ('unit_service_fee', models.DecimalField(decimal_places=2, default=0, max_digits=10, validators=[django.core.validators.MinValueValidator(0)], verbose_name='unit service fee')),
                ('subtotal', models.DecimalField(decimal_places=2, max_digits=10, validators=[django.core.validators.MinValueValidator(0)], verbose_name='subtotal')),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='events.order', verbose_name='order')),
            ],
            options={
                'verbose_name': 'order item',
                'verbose_name_plural': 'order items',
            },
        ),
        migrations.AlterModelOptions(
            name='tickettier',
            options={'ordering': ['order', 'price'], 'verbose_name': 'ticket tier', 'verbose_name_plural': 'ticket tiers'},
        ),
        migrations.RemoveField(
            model_name='tickettier',
            name='category_description',
        ),
        migrations.AddField(
            model_name='event',
            name='cart_adds_count',
            field=models.PositiveIntegerField(default=0, verbose_name='cart adds count'),
        ),
        migrations.AddField(
            model_name='event',
            name='conversion_count',
            field=models.PositiveIntegerField(default=0, verbose_name='conversion count'),
        ),
        migrations.AddField(
            model_name='event',
            name='password',
            field=models.CharField(blank=True, help_text='Password for private events', max_length=100, null=True, verbose_name='password'),
        ),
        migrations.AddField(
            model_name='event',
            name='template',
            field=models.CharField(choices=[('standard', 'Standard'), ('multi_day', 'Multi-Day'), ('multi_session', 'Multi-Session'), ('seated', 'Seated')], default='standard', max_length=20, verbose_name='template'),
        ),
        migrations.AddField(
            model_name='event',
            name='views_count',
            field=models.PositiveIntegerField(default=0, verbose_name='views count'),
        ),
        migrations.AddField(
            model_name='event',
            name='visibility',
            field=models.CharField(choices=[('public', 'Public'), ('private', 'Private'), ('password', 'Password Protected')], default='public', max_length=20, verbose_name='visibility'),
        ),
        migrations.AddField(
            model_name='tickettier',
            name='order',
            field=models.PositiveIntegerField(default=0, verbose_name='order'),
        ),
        migrations.AlterField(
            model_name='event',
            name='status',
            field=models.CharField(choices=[('draft', 'Draft'), ('active', 'Active'), ('completed', 'Completed'), ('cancelled', 'Cancelled')], default='draft', max_length=20, verbose_name='status'),
        ),
        migrations.AlterField(
            model_name='event',
            name='type',
            field=models.CharField(choices=[('conference', 'Conference'), ('concert', 'Concert'), ('sports', 'Sports'), ('theater', 'Theater'), ('workshop', 'Workshop'), ('festival', 'Festival'), ('party', 'Party'), ('other', 'Other')], default='other', max_length=20, verbose_name='type'),
        ),
        migrations.AlterField(
            model_name='tickettier',
            name='type',
            field=models.CharField(choices=[('general', 'General'), ('vip', 'VIP'), ('early-bird', 'Early Bird'), ('group', 'Group'), ('student', 'Student'), ('child', 'Child'), ('senior', 'Senior')], default='general', max_length=20, verbose_name='type'),
        ),
        migrations.CreateModel(
            name='TicketCategory',
            fields=[
                ('tenant_id', models.CharField(db_index=True, max_length=50)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated at')),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=100, verbose_name='name')),
                ('description', models.TextField(blank=True, verbose_name='description')),
                ('capacity', models.PositiveIntegerField(default=0, verbose_name='capacity')),
                ('sold', models.PositiveIntegerField(default=0, verbose_name='sold')),
                ('status', models.CharField(choices=[('active', 'Active'), ('hidden', 'Hidden'), ('sold_out', 'Sold Out')], default='active', max_length=20, verbose_name='status')),
                ('visibility', models.CharField(choices=[('public', 'Public'), ('private', 'Private'), ('password', 'Password Protected')], default='public', max_length=20, verbose_name='visibility')),
                ('color', models.CharField(default='#3b82f6', max_length=20, verbose_name='color')),
                ('order', models.PositiveIntegerField(default=0, verbose_name='order')),
                ('max_per_purchase', models.PositiveIntegerField(default=10, verbose_name='max per purchase')),
                ('min_per_purchase', models.PositiveIntegerField(default=1, verbose_name='min per purchase')),
                ('sale_start_date', models.DateField(blank=True, null=True, verbose_name='sale start date')),
                ('sale_end_date', models.DateField(blank=True, null=True, verbose_name='sale end date')),
                ('sale_start_time', models.TimeField(blank=True, null=True, verbose_name='sale start time')),
                ('sale_end_time', models.TimeField(blank=True, null=True, verbose_name='sale end time')),
                ('access_start_date', models.DateField(blank=True, null=True, verbose_name='access start date')),
                ('access_end_date', models.DateField(blank=True, null=True, verbose_name='access end date')),
                ('access_start_time', models.TimeField(blank=True, null=True, verbose_name='access start time')),
                ('access_end_time', models.TimeField(blank=True, null=True, verbose_name='access end time')),
                ('event', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ticket_categories', to='events.event', verbose_name='event')),
            ],
            options={
                'verbose_name': 'ticket category',
                'verbose_name_plural': 'ticket categories',
                'ordering': ['order'],
            },
        ),
        migrations.CreateModel(
            name='Ticket',
            fields=[
                ('tenant_id', models.CharField(db_index=True, max_length=50)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated at')),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('ticket_number', models.CharField(default=apps.events.models.generate_ticket_number, max_length=50, unique=True, verbose_name='ticket number')),
                ('first_name', models.CharField(max_length=100, verbose_name='first name')),
                ('last_name', models.CharField(max_length=100, verbose_name='last name')),
                ('email', models.EmailField(max_length=254, verbose_name='email')),
                ('status', models.CharField(choices=[('active', 'Active'), ('used', 'Used'), ('cancelled', 'Cancelled'), ('refunded', 'Refunded')], default='active', max_length=20, verbose_name='status')),
                ('checked_in', models.BooleanField(default=False, verbose_name='checked in')),
                ('check_in_time', models.DateTimeField(blank=True, null=True, verbose_name='check in time')),
                ('form_data', models.JSONField(blank=True, default=dict, help_text='Form data collected for this ticket', verbose_name='form data')),
                ('order_item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='tickets', to='events.orderitem', verbose_name='order item')),
            ],
            options={
                'verbose_name': 'ticket',
                'verbose_name_plural': 'tickets',
            },
        ),
        migrations.AddField(
            model_name='orderitem',
            name='ticket_tier',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='order_items', to='events.tickettier', verbose_name='ticket tier'),
        ),
        migrations.AddField(
            model_name='order',
            name='event',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='orders', to='events.event', verbose_name='event'),
        ),
        migrations.AddField(
            model_name='order',
            name='user',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='orders', to=settings.AUTH_USER_MODEL, verbose_name='user'),
        ),
        migrations.CreateModel(
            name='FormField',
            fields=[
                ('tenant_id', models.CharField(db_index=True, max_length=50)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated at')),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('label', models.CharField(max_length=100, verbose_name='label')),
                ('type', models.CharField(choices=[('text', 'Text'), ('email', 'Email'), ('number', 'Number'), ('select', 'Select'), ('checkbox', 'Checkbox'), ('radio', 'Radio'), ('date', 'Date'), ('time', 'Time'), ('phone', 'Phone')], default='text', max_length=20, verbose_name='type')),
                ('required', models.BooleanField(default=False, verbose_name='required')),
                ('placeholder', models.CharField(blank=True, max_length=100, verbose_name='placeholder')),
                ('help_text', models.CharField(blank=True, max_length=255, verbose_name='help text')),
                ('order', models.PositiveIntegerField(default=0, verbose_name='order')),
                ('options', models.TextField(blank=True, help_text='Comma-separated options for select, checkbox, radio', verbose_name='options')),
                ('form', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='fields', to='events.eventform', verbose_name='form')),
            ],
            options={
                'verbose_name': 'form field',
                'verbose_name_plural': 'form fields',
                'ordering': ['order'],
            },
        ),
        migrations.CreateModel(
            name='EventCommunication',
            fields=[
                ('tenant_id', models.CharField(db_index=True, max_length=50)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated at')),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=100, verbose_name='name')),
                ('type', models.CharField(choices=[('confirmation', 'Order Confirmation'), ('reminder', 'Event Reminder'), ('update', 'Event Update'), ('cancellation', 'Event Cancellation'), ('thank_you', 'Thank You'), ('custom', 'Custom')], default='custom', max_length=20, verbose_name='type')),
                ('subject', models.CharField(max_length=255, verbose_name='subject')),
                ('content', models.TextField(verbose_name='content')),
                ('status', models.CharField(choices=[('draft', 'Draft'), ('scheduled', 'Scheduled'), ('sent', 'Sent'), ('failed', 'Failed')], default='draft', max_length=20, verbose_name='status')),
                ('scheduled_date', models.DateTimeField(blank=True, null=True, verbose_name='scheduled date')),
                ('sent_date', models.DateTimeField(blank=True, null=True, verbose_name='sent date')),
                ('recipients_count', models.PositiveIntegerField(default=0, verbose_name='recipients count')),
                ('delivery_count', models.PositiveIntegerField(default=0, verbose_name='delivery count')),
                ('open_count', models.PositiveIntegerField(default=0, verbose_name='open count')),
                ('click_count', models.PositiveIntegerField(default=0, verbose_name='click count')),
                ('event', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='communications', to='events.event', verbose_name='event')),
            ],
            options={
                'verbose_name': 'event communication',
                'verbose_name_plural': 'event communications',
            },
        ),
        migrations.AddField(
            model_name='coupon',
            name='event',
            field=models.ForeignKey(blank=True, help_text='If null, coupon applies to all events by this organizer', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='coupons', to='events.event', verbose_name='event'),
        ),
        migrations.AddField(
            model_name='coupon',
            name='organizer',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='coupons', to='organizers.organizer', verbose_name='organizer'),
        ),
        migrations.AddField(
            model_name='coupon',
            name='ticket_categories',
            field=models.ManyToManyField(blank=True, related_name='coupons', to='events.ticketcategory', verbose_name='applicable ticket categories'),
        ),
        migrations.AddField(
            model_name='coupon',
            name='ticket_tiers',
            field=models.ManyToManyField(blank=True, related_name='coupons', to='events.tickettier', verbose_name='applicable ticket tiers'),
        ),
        migrations.AddField(
            model_name='tickettier',
            name='form',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ticket_tiers', to='events.eventform', verbose_name='form'),
        ),
        migrations.AlterField(
            model_name='tickettier',
            name='category',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ticket_tiers', to='events.ticketcategory', verbose_name='category'),
        ),
    ]
