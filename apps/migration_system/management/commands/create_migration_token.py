"""
Management command para crear tokens de migración.
"""

from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth import get_user_model
from apps.migration_system.models import MigrationToken

User = get_user_model()


class Command(BaseCommand):
    help = 'Crea un token de autenticación para operaciones de migración'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--description',
            required=True,
            help='Descripción del token'
        )
        parser.add_argument(
            '--permissions',
            default='read_write',
            choices=['read', 'write', 'read_write', 'admin'],
            help='Permisos del token (default: read_write)'
        )
        parser.add_argument(
            '--expires-in',
            default='24h',
            help='Tiempo de expiración (ej: 24h, 7d, 30d) (default: 24h)'
        )
        parser.add_argument(
            '--single-use',
            action='store_true',
            help='Token de un solo uso'
        )
        parser.add_argument(
            '--allowed-ips',
            help='IPs permitidas (comma-separated)'
        )
        parser.add_argument(
            '--allowed-domains',
            help='Dominios permitidos (comma-separated)'
        )
        parser.add_argument(
            '--user-email',
            help='Email del usuario que crea el token (default: primer superuser)'
        )
    
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🔐 Creando token de migración...'))
        self.stdout.write('')
        
        # Obtener usuario
        if options.get('user_email'):
            try:
                user = User.objects.get(email=options['user_email'])
            except User.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Usuario no encontrado: {options['user_email']}"))
                return
        else:
            # Usar primer superuser
            user = User.objects.filter(is_superuser=True).first()
            if not user:
                self.stdout.write(self.style.ERROR('No hay superusers. Especifica --user-email'))
                return
        
        # Parsear expiración
        expires_in_str = options['expires_in']
        if expires_in_str.endswith('h'):
            hours = int(expires_in_str[:-1])
            expires_at = timezone.now() + timedelta(hours=hours)
        elif expires_in_str.endswith('d'):
            days = int(expires_in_str[:-1])
            expires_at = timezone.now() + timedelta(days=days)
        else:
            self.stdout.write(self.style.ERROR('Formato de expiración inválido. Usa: 24h, 7d, 30d'))
            return
        
        # Parsear IPs y dominios permitidos
        allowed_ips = []
        if options.get('allowed_ips'):
            allowed_ips = [ip.strip() for ip in options['allowed_ips'].split(',')]
        
        allowed_domains = []
        if options.get('allowed_domains'):
            allowed_domains = [domain.strip() for domain in options['allowed_domains'].split(',')]
        
        # Crear token
        token = MigrationToken.objects.create(
            token=MigrationToken.generate_token(),
            description=options['description'],
            permissions=options['permissions'],
            expires_at=expires_at,
            is_single_use=options.get('single_use', False),
            allowed_ips=allowed_ips,
            allowed_domains=allowed_domains,
            created_by=user
        )
        
        self.stdout.write(self.style.SUCCESS('✅ Token creado exitosamente!'))
        self.stdout.write('')
        self.stdout.write('📋 DETALLES DEL TOKEN:')
        self.stdout.write('=' * 60)
        self.stdout.write(f"Token: {token.token}")
        self.stdout.write('=' * 60)
        self.stdout.write(f"ID: {token.id}")
        self.stdout.write(f"Descripción: {token.description}")
        self.stdout.write(f"Permisos: {token.get_permissions_display()}")
        self.stdout.write(f"Expira: {token.expires_at.strftime('%Y-%m-%d %H:%M:%S')}")
        self.stdout.write(f"Un solo uso: {'Sí' if token.is_single_use else 'No'}")
        
        if allowed_ips:
            self.stdout.write(f"IPs permitidas: {', '.join(allowed_ips)}")
        
        if allowed_domains:
            self.stdout.write(f"Dominios permitidos: {', '.join(allowed_domains)}")
        
        self.stdout.write(f"Creado por: {user.email}")
        self.stdout.write('')
        self.stdout.write('⚠️  IMPORTANTE:')
        self.stdout.write('  - Guarda este token en un lugar seguro')
        self.stdout.write('  - No lo compartas')
        self.stdout.write('  - No lo subas a Git')
        self.stdout.write('')
        self.stdout.write('💡 USO:')
        self.stdout.write('  En headers HTTP:')
        self.stdout.write(f'    Authorization: MigrationToken {token.token}')
        self.stdout.write('')
        self.stdout.write('  En comandos:')
        self.stdout.write(f'    --source-token {token.token}')
        self.stdout.write(f'    --target-token {token.token}')
        self.stdout.write('')
