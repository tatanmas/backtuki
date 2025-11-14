from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from .models import OTP, OTPAttempt


@admin.register(OTP)
class OTPAdmin(admin.ModelAdmin):
    list_display = [
        'code', 'email', 'purpose', 'user', 'status_badge', 
        'created_at', 'expires_at', 'attempts'
    ]
    list_filter = [
        'purpose', 'is_used', 'created_at', 'expires_at'
    ]
    search_fields = ['email', 'code', 'user__email']
    readonly_fields = [
        'code', 'created_at', 'used_at', 'time_remaining_display',
        'attempts', 'metadata'
    ]
    ordering = ['-created_at']
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('email', 'code', 'purpose', 'user')
        }),
        ('Estado y Tiempos', {
            'fields': ('is_used', 'created_at', 'expires_at', 'used_at', 'time_remaining_display')
        }),
        ('Seguridad', {
            'fields': ('attempts', 'ip_address', 'user_agent')
        }),
        ('Metadatos', {
            'fields': ('metadata',),
            'classes': ('collapse',)
        })
    )
    
    def status_badge(self, obj):
        if obj.is_used:
            return format_html(
                '<span style="color: green; font-weight: bold;">✓ Usado</span>'
            )
        elif obj.is_expired:
            return format_html(
                '<span style="color: red; font-weight: bold;">✗ Expirado</span>'
            )
        else:
            return format_html(
                '<span style="color: blue; font-weight: bold;">⏳ Activo</span>'
            )
    status_badge.short_description = 'Estado'
    
    def time_remaining_display(self, obj):
        if obj.is_expired:
            return "Expirado"
        elif obj.is_used:
            return "Usado"
        else:
            remaining = obj.time_remaining
            minutes = int(remaining.total_seconds() // 60)
            seconds = int(remaining.total_seconds() % 60)
            return f"{minutes}m {seconds}s"
    time_remaining_display.short_description = 'Tiempo restante'
    
    actions = ['invalidate_codes', 'cleanup_expired']
    
    def invalidate_codes(self, request, queryset):
        count = 0
        for otp in queryset.filter(is_used=False):
            otp.invalidate()
            count += 1
        self.message_user(request, f'{count} códigos invalidados')
    invalidate_codes.short_description = 'Invalidar códigos seleccionados'
    
    def cleanup_expired(self, request, queryset):
        count = OTP.objects.cleanup_expired()
        self.message_user(request, f'{count} códigos expirados eliminados')
    cleanup_expired.short_description = 'Limpiar códigos expirados'


@admin.register(OTPAttempt)
class OTPAttemptAdmin(admin.ModelAdmin):
    list_display = [
        'otp', 'attempted_code', 'is_successful', 
        'ip_address', 'attempted_at'
    ]
    list_filter = ['is_successful', 'attempted_at']
    search_fields = ['otp__email', 'otp__code', 'attempted_code', 'ip_address']
    readonly_fields = ['attempted_at']
    ordering = ['-attempted_at']
    
    def has_add_permission(self, request):
        return False  # No permitir crear intentos manualmente
