"""
Views para creación de eventos públicos sin autenticación previa.
Similar al flujo de Luma - crear evento primero, validar email después.
"""

from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.parsers import MultiPartParser, FormParser
from django.db import transaction
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.text import slugify
from django.conf import settings
import uuid
import os

from apps.otp.models import OTP, OTPPurpose
from apps.otp.services import OTPService
from apps.organizers.models import Organizer, OrganizerUser
from apps.events.models import Event, Location, ComplimentaryTicketInvitation
from apps.forms.models import Form
from apps.forms.serializers import FormSerializer
from .serializers import (
    PublicEventCreateSerializer,
    EventDetailSerializer,
    PublicComplimentaryTicketInvitationSerializer,
    ComplimentaryTicketInvitationRedeemSerializer,
)
from apps.events.services.complimentary import redeem_invitation
from django.shortcuts import get_object_or_404
from django.http import Http404

User = get_user_model()


class PublicEventViewSet(viewsets.ModelViewSet):
    """
    ViewSet para creación de eventos sin autenticación previa.
    Similar al flujo de Luma - permite crear eventos y validar email después.
    """
    permission_classes = [AllowAny]
    serializer_class = PublicEventCreateSerializer
    
    def get_queryset(self):
        """Solo eventos públicos para consulta."""
        return Event.objects.filter(
            status='published', 
            visibility='public',
            requires_email_validation=False,
            deleted_at__isnull=True  # Exclude soft deleted events
        )
    
    def get_object(self):
        """
        Sobrescribir get_object para permitir acceso a eventos en draft
        que requieren validación de email (para el flujo público).
        """
        if self.action in ['send_validation_otp', 'validate_and_publish', 'update', 'partial_update', 'associate_image']:
            # Para acciones de validación y actualización, permitir acceso a eventos en draft
            lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
            lookup_value = self.kwargs[lookup_url_kwarg]
            filter_kwargs = {self.lookup_field: lookup_value}
            
            try:
                obj = Event.objects.get(**filter_kwargs)
                
                # Check if event is soft deleted
                if obj.deleted_at is not None:
                    from django.http import Http404
                    raise Http404("Evento no encontrado")
                
                # ✅ MEJORADO: Permitir acceso si:
                # 1. Requiere validación (está en draft) O
                # 2. Ya fue validado/publicado (para actualizaciones posteriores)
                # 3. Para update/partial_update, permitir acceso a eventos publicados si hay autenticación
                if (obj.requires_email_validation and obj.organizer and obj.organizer.is_temporary) or \
                   (not obj.requires_email_validation and obj.organizer and not obj.organizer.is_temporary) or \
                   (self.action in ['update', 'partial_update'] and not obj.requires_email_validation):
                    return obj
                else:
                    from django.http import Http404
                    raise Http404("Evento no encontrado o no requiere validación")
            except Event.DoesNotExist:
                from django.http import Http404
                raise Http404("Evento no encontrado")
        
        # Para otras acciones, usar el queryset normal
        return super().get_object()
    
    def get_serializer_class(self):
        """Usar serializer apropiado según la acción."""
        if self.action in ['retrieve', 'list']:
            return EventDetailSerializer
        elif self.action in ['update', 'partial_update']:
            return PublicEventCreateSerializer  # Reuse create serializer for updates
        return PublicEventCreateSerializer
    
    def create(self, request, *args, **kwargs):
        """
        Crear evento público con organizador temporal.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Crear organizador temporal con datos mínimos
        temp_organizer = self.create_temp_organizer()
        
        # Crear evento como borrador
        event = serializer.save(
            organizer=temp_organizer,
            status='draft',
            requires_email_validation=True
        )
        
        return Response({
            'event_id': str(event.id),
            'organizer_id': str(temp_organizer.id),
            'message': 'Borrador de evento creado exitosamente. Por favor, valida tu email para continuar.'
        }, status=status.HTTP_201_CREATED)
    
    def update(self, request, *args, **kwargs):
        """
        🚀 ENTERPRISE UPDATE: Actualizar evento público.
        Permite actualizar eventos en draft Y publicados.
        """
        try:
            instance = self.get_object()
            
            # ✅ SECURITY: Validar permisos según el estado del evento
            can_update = False
            
            if instance.requires_email_validation:
                # Evento en draft - permitir sin autenticación (flujo público)
                can_update = True
                print(f"[PUBLIC-EVENT-UPDATE] 📝 Updating draft event (no auth required): {instance.id}")
            elif request.user.is_authenticated:
                # Evento publicado - validar que sea el organizador propietario o superadmin
                user = request.user
                
                # Verificar si es superadmin
                if user.is_superuser:
                    can_update = True
                    print(f"[PUBLIC-EVENT-UPDATE] 🔐 Superadmin updating published event: {instance.id}")
                else:
                    # Verificar si es el organizador propietario del evento
                    try:
                        from apps.organizers.models import OrganizerUser
                        organizer_user = OrganizerUser.objects.get(
                            user=user,
                            organizer=instance.organizer
                        )
                        can_update = True
                        print(f"[PUBLIC-EVENT-UPDATE] ✅ Organizer updating own published event: {instance.id}")
                    except OrganizerUser.DoesNotExist:
                        can_update = False
                        print(f"[PUBLIC-EVENT-UPDATE] ❌ User {user.id} is not the organizer of event {instance.id}")
            else:
                can_update = False
                print(f"[PUBLIC-EVENT-UPDATE] ❌ No permission to update published event: {instance.id}")
            
            if not can_update:
                return Response({
                    'success': False,
                    'message': 'No tienes permisos para actualizar este evento'
                }, status=status.HTTP_403_FORBIDDEN)
            
            print(f"[PUBLIC-EVENT-UPDATE] 🔄 Updating public event: {instance.id}")
            print(f"[PUBLIC-EVENT-UPDATE] 📊 Update data: {request.data}")
            
            # Usar el serializer para validar y actualizar
            serializer = self.get_serializer(instance, data=request.data, partial=kwargs.get('partial', False))
            serializer.is_valid(raise_exception=True)
            
            # Actualizar el evento
            updated_event = serializer.save()
            
            print(f"[PUBLIC-EVENT-UPDATE] ✅ Event updated successfully: {updated_event.id}")
            
            return Response({
                'success': True,
                'message': 'Evento actualizado exitosamente',
                'event_id': str(updated_event.id),
                'data': serializer.data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            print(f"[PUBLIC-EVENT-UPDATE] ❌ Error updating event: {e}")
            return Response({
                'success': False,
                'message': f'Error al actualizar el evento: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)
    
    def partial_update(self, request, *args, **kwargs):
        """
        Actualización parcial de evento público.
        """
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)
    
    def create_temp_organizer(self):
        """Crear organizador temporal con datos mínimos."""
        # Generar slug único temporal
        temp_slug = f"temp-{uuid.uuid4().hex[:8]}"
        
        organizer = Organizer.objects.create(
            name="Organizador Temporal",
            slug=temp_slug,
            contact_email="",  # Se completará con OTP
            status='pending_validation',
            onboarding_completed=False,
            is_temporary=True,
            email_validated=False
        )
        
        return organizer
    
    @action(detail=True, methods=['post'], url_path='validate-email')
    def validate_and_publish(self, request, pk=None):
        """
        Validar email con OTP y publicar evento.
        Este es el punto donde se completa el organizador.
        """
        event = self.get_object()
        email = request.data.get('email')
        otp_code = request.data.get('code') or request.data.get('otp_code')
        
        if not email or not otp_code:
            return Response({
                'success': False,
                'message': 'Email y código OTP son requeridos'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # ✅ NUEVO: Verificar si el evento ya fue validado
        if not event.requires_email_validation and event.organizer and not event.organizer.is_temporary:
            print(f"[PublicEventValidation] ℹ️ Event already validated, returning existing token for: {email}")
            
            # Buscar el usuario existente
            try:
                user = User.objects.get(email__iexact=email)
                
                # Generar nuevo token de autenticación
                from rest_framework_simplejwt.tokens import RefreshToken
                refresh = RefreshToken.for_user(user)
                access_token = str(refresh.access_token)
                
                return Response({
                    'success': True,
                    'message': 'Evento ya validado previamente. Aquí tienes tu token de acceso.',
                    'event_id': str(event.id),
                    'organizer_id': str(event.organizer.id),
                    'user_id': str(user.id),
                    'user_token': access_token,
                    'is_new_user': False,
                    'already_validated': True
                })
            except User.DoesNotExist:
                return Response({
                    'success': False,
                    'message': 'Usuario no encontrado para este evento ya validado'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validar OTP
        result = OTPService.validate_code(
            email=email,
            code=otp_code,
            purpose=OTPPurpose.EVENT_CREATION
        )
        
        if not result['success']:
            return Response({
                'success': False,
                'message': result['message']
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Verificar si ya existe un organizador para este email
        with transaction.atomic():
            # Buscar si ya existe un organizador con este email
            existing_organizer = None
            try:
                existing_organizer = Organizer.objects.get(contact_email=email, is_temporary=False)
                print(f"[PublicEventValidation] ✅ Found existing organizer: {existing_organizer.name} (ID: {existing_organizer.id})")
            except Organizer.DoesNotExist:
                print(f"[PublicEventValidation] ℹ️ No existing organizer found for email: {email}")
            except Organizer.MultipleObjectsReturned:
                # Si hay múltiples organizadores, tomar el más reciente
                existing_organizer = Organizer.objects.filter(contact_email=email, is_temporary=False).order_by('-created_at').first()
                print(f"[PublicEventValidation] ⚠️ Multiple organizers found, using most recent: {existing_organizer.name} (ID: {existing_organizer.id})")
            
            if existing_organizer:
                # Usar el organizador existente
                organizer = existing_organizer
                print(f"[PublicEventValidation] 🔄 Associating event with existing organizer: {organizer.name}")
                
                # Actualizar el evento para usar el organizador existente
                event.organizer = organizer
                event.requires_email_validation = False
                event.save()
                
                # Buscar o crear el usuario
                user, user_created = User.objects.get_or_create(
                    email=email,
                    defaults={
                        'is_organizer': True,
                        'is_staff': True
                    }
                )
                
                # Actualizar usuario si ya existía
                if not user_created:
                    user.is_organizer = True
                    user.is_staff = True
                    user.save()
                
                # Verificar si ya existe la relación organizador-usuario
                organizer_user, ou_created = OrganizerUser.objects.get_or_create(
                    organizer=organizer,
                    user=user,
                    defaults={
                        'is_admin': True,
                        'can_manage_events': True,
                        'can_manage_accommodations': True,
                        'can_manage_experiences': True,
                        'can_view_reports': True,
                        'can_manage_settings': True
                    }
                )
                
                # ✅ ARREGLAR: Definir is_new_user para organizador existente
                is_new_user = user_created
                
                if ou_created:
                    print(f"[PublicEventValidation] ✅ Created new OrganizerUser relationship")
                else:
                    print(f"[PublicEventValidation] ℹ️ OrganizerUser relationship already exists")
                    
            else:
                # Crear nuevo organizador (lógica original)
                print(f"[PublicEventValidation] 🆕 Creating new organizer for email: {email}")
                organizer = event.organizer
                
                # Actualizar organizador con datos reales
                organizer.contact_email = email
                organizer.name = f"Organizador {email.split('@')[0].title()}"
                organizer.status = 'active'
                organizer.is_temporary = False
                organizer.email_validated = True
                # IMPORTANTE: onboarding_completed = False para que el usuario complete el modal de perfil
                # El modal aparecerá cuando el usuario inicie sesión hasta que complete sus datos
                organizer.onboarding_completed = False
                
                # Generar slug definitivo
                base_slug = slugify(organizer.name)
                counter = 1
                final_slug = base_slug
                while Organizer.objects.filter(slug=final_slug).exclude(id=organizer.id).exists():
                    final_slug = f"{base_slug}-{counter}"
                    counter += 1
                organizer.slug = final_slug
                
                organizer.save()
                
                # Crear usuario si no existe
                user, user_created = User.objects.get_or_create(
                    email=email,
                    defaults={
                        'username': email,  # 🚀 FIX: Use email as username to avoid duplicates
                        'is_organizer': True,
                        'is_staff': True
                    }
                )
                
                # Actualizar usuario si ya existía
                if not user_created:
                    user.is_organizer = True
                    user.is_staff = True
                    user.save()
                
                # Crear relación organizador-usuario
                organizer_user, ou_created = OrganizerUser.objects.get_or_create(
                    organizer=organizer,
                    user=user,
                    defaults={
                        'is_admin': True,
                        'can_manage_events': True,
                        'can_manage_accommodations': True,
                        'can_manage_experiences': True,
                        'can_view_reports': True,
                        'can_manage_settings': True
                    }
                )
                
                # ✅ ARREGLAR: Definir is_new_user para organizador nuevo
                is_new_user = user_created
            
            # Publicar evento
            event.status = 'published'
            event.requires_email_validation = False
            event.save()
            
            # 🚀 ENTERPRISE: Vincular imágenes del evento a la biblioteca de medios del organizador
            try:
                from apps.events.models import EventImage
                from apps.media.models import MediaAsset, MediaUsage
                from django.contrib.contenttypes.models import ContentType
                from django.core.files.storage import default_storage
                from django.core.files.base import ContentFile
                
                # Obtener todas las imágenes del evento
                event_images = EventImage.objects.filter(event=event)
                
                print(f"[PublicEventValidation] 📸 Linking {event_images.count()} images to media library for organizer {organizer.id}")
                
                for event_image in event_images:
                    try:
                        # Obtener la ruta del archivo del EventImage
                        file_path = event_image.image.name if hasattr(event_image.image, 'name') else str(event_image.image)
                        
                        # Leer el archivo desde storage
                        if default_storage.exists(file_path):
                            with default_storage.open(file_path, 'rb') as f:
                                file_content = f.read()
                                
                                # Obtener el nombre original del archivo
                                original_filename = event_image.alt or file_path.split('/')[-1]
                                if not original_filename or '.' not in original_filename:
                                    # Si no hay extensión, intentar obtenerla del content type o usar .jpg por defecto
                                    ext = 'jpg'
                                    if hasattr(event_image.image, 'content_type'):
                                        content_type = event_image.image.content_type
                                        if 'png' in content_type:
                                            ext = 'png'
                                        elif 'webp' in content_type:
                                            ext = 'webp'
                                        elif 'gif' in content_type:
                                            ext = 'gif'
                                    original_filename = f"{original_filename}.{ext}" if '.' not in original_filename else original_filename
                                
                                # Crear MediaAsset usando el archivo
                                asset = MediaAsset(
                                    scope='organizer',
                                    organizer=organizer,
                                    uploaded_by=user,
                                    original_filename=original_filename
                                )
                                
                                # Asignar el archivo usando ContentFile para que Django lo guarde correctamente
                                asset.file.save(
                                    original_filename,
                                    ContentFile(file_content),
                                    save=False
                                )
                                
                                # Obtener el tamaño del archivo
                                try:
                                    asset.size_bytes = len(file_content)
                                except:
                                    asset.size_bytes = default_storage.size(file_path) if hasattr(default_storage, 'size') else 0
                                
                                # Guardar el asset (esto también extraerá los metadatos de la imagen)
                                asset.save()
                                
                                print(f"[PublicEventValidation] ✅ Created MediaAsset {asset.id} from EventImage {event_image.id}")
                                
                                # Crear MediaUsage para rastrear el uso
                                content_type = ContentType.objects.get_for_model(event.__class__)
                                MediaUsage.objects.create(
                                    asset=asset,
                                    content_type=content_type,
                                    object_id=event.id,
                                    field_name=f"image_{event_image.type or 'image'}"
                                )
                                
                                print(f"[PublicEventValidation] ✅ Created MediaUsage for asset {asset.id} on event {event.id}")
                        else:
                            print(f"[PublicEventValidation] ⚠️ File not found in storage: {file_path}")
                            
                    except Exception as img_error:
                        # Log error pero continuar con otras imágenes
                        print(f"[PublicEventValidation] ⚠️ Error linking image {event_image.id}: {img_error}")
                        import traceback
                        traceback.print_exc()
                        
            except Exception as e:
                # Log error pero no fallar la validación
                print(f"[PublicEventValidation] ⚠️ Error linking images to media library: {e}")
                import traceback
                traceback.print_exc()
            
            # Generar token de autenticación
            from rest_framework_simplejwt.tokens import RefreshToken
            refresh = RefreshToken.for_user(user)
            access_token = str(refresh.access_token)
        
        return Response({
            'success': True,
            'message': 'Evento publicado exitosamente',
            'event_id': str(event.id),
            'organizer_id': str(organizer.id),
            'user_id': str(user.id),
            'user_token': access_token,
            'is_new_user': is_new_user
        })
    
    @action(detail=True, methods=['post'], url_path='associate-image')
    def associate_image(self, request, pk=None):
        """
        🚀 ENTERPRISE: Asociar una imagen ya subida a un evento público.
        Útil cuando la imagen se subió antes de crear el evento.
        """
        event = self.get_object()
        file_path = request.data.get('file_path')
        
        if not file_path:
            return Response({
                'success': False,
                'message': 'file_path es requerido'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Verificar que el evento requiere validación (está en draft)
        if not (event.organizer and event.organizer.is_temporary and event.requires_email_validation):
            return Response({
                'success': False,
                'message': 'Solo se pueden asociar imágenes a eventos en draft'
            }, status=status.HTTP_403_FORBIDDEN)
        
        from django.core.files.storage import default_storage
        from apps.events.models import EventImage
        
        try:
            # Verificar que el archivo existe
            if not default_storage.exists(file_path):
                return Response({
                    'success': False,
                    'message': 'El archivo no existe'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Obtener la URL del archivo
            file_url = default_storage.url(file_path)
            
            # Crear EventImage record
            event_image = EventImage.objects.create(
                event=event,
                image=file_path,
                alt=request.data.get('alt', file_path.split('/')[-1]),
                type=request.data.get('type', 'image'),
                order=event.images.count()
            )
            
            print(f"[PUBLIC-ASSOCIATE] ✅ Created EventImage {event_image.id} for event {event.id} from path {file_path}")
            
            return Response({
                'success': True,
                'url': file_url,
                'event_image_id': str(event_image.id),
                'message': 'Imagen asociada al evento exitosamente'
            })
            
        except Exception as e:
            print(f"[PUBLIC-ASSOCIATE] ❌ Error associating image: {e}")
            import traceback
            traceback.print_exc()
            return Response({
                'success': False,
                'message': f'Error al asociar la imagen: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['post'])
    def send_validation_otp(self, request, pk=None):
        """
        Enviar código OTP para validar email del organizador.
        """
        event = self.get_object()
        email = request.data.get('email')
        
        if not email:
            return Response({
                'success': False,
                'message': 'Email es requerido'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Verificar que el evento requiere validación
        if not event.requires_email_validation:
            return Response({
                'success': False,
                'message': 'Este evento ya ha sido validado'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Buscar usuario existente
        user = None
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            pass
        
        # Metadatos específicos para eventos
        metadata = {
            'event_id': str(event.id),
            'event_title': event.title,
            'creation_flow': 'public_quick'
        }
        
        # Generar y enviar OTP
        result = OTPService.generate_and_send(
            email=email,
            purpose=OTPPurpose.EVENT_CREATION,
            user=user,
            metadata=metadata,
            request=request
        )
        
        if result['success']:
            otp = result['otp']
            return Response({
                'success': True,
                'message': 'Código enviado para validar tu evento',
                'expires_at': otp.expires_at,
                'time_remaining_minutes': int(otp.time_remaining.total_seconds() // 60),
                'is_new_organizer': user is None
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'success': False,
                'message': result['message']
            }, status=status.HTTP_400_BAD_REQUEST)
    
    def retrieve(self, request, *args, **kwargs):
        """
        Obtener detalles de un evento público.
        """
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return Response(serializer.data)
        except Event.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Evento no encontrado'
            }, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=False, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def upload(self, request):
        """🚀 ENTERPRISE PUBLIC IMAGE UPLOAD - Upload an image file for public events."""
        if 'file' not in request.FILES:
            return Response({'detail': 'No file found'}, status=status.HTTP_400_BAD_REQUEST)
        
        file_obj = request.FILES['file']
        event_id = request.data.get('event_id')  # Optional event association
        
        # Generate a unique filename
        filename = f"{uuid.uuid4().hex}.{file_obj.name.split('.')[-1]}"
        
        # 🚀 ENTERPRISE: Use Django's configured storage backend (local in dev, GCS in prod)
        from django.core.files.storage import default_storage
        
        try:
            # Save file using Django's storage backend (automatically uses correct storage)
            file_path = f"event_images/{filename}"
            saved_path = default_storage.save(file_path, file_obj)
            
            # Get the full URL for the uploaded file
            file_url = default_storage.url(saved_path)
            
            print(f"[PUBLIC-UPLOAD] ✅ File uploaded to: {saved_path}")
            print(f"[PUBLIC-UPLOAD] ✅ File URL: {file_url}")
            
            # If event_id is provided, create EventImage record for public events
            if event_id:
                try:
                    event = Event.objects.get(id=event_id)
                    
                    # For public events, only check if it's a temporary organizer (no auth required)
                    if not (event.organizer and event.organizer.is_temporary and event.requires_email_validation):
                        # Clean up uploaded file if not a public event
                        try:
                            default_storage.delete(saved_path)
                        except Exception as e:
                            print(f"[PUBLIC-UPLOAD] ⚠️ Could not delete file {saved_path}: {e}")
                        return Response({'detail': 'Only public events in draft can upload images without authentication'}, 
                                      status=status.HTTP_403_FORBIDDEN)
                    
                    # Import EventImage here to avoid circular imports
                    from apps.events.models import EventImage
                    
                    # Create EventImage record
                    event_image = EventImage.objects.create(
                        event=event,
                        image=saved_path,  # Store the path returned by storage backend
                        alt=request.data.get('alt', file_obj.name),
                        type=request.data.get('type', 'image'),
                        order=event.images.count()  # Set order as current count
                    )
                    
                    print(f"[PUBLIC-UPLOAD] ✅ Created EventImage record: {event_image.id} for public event {event.id}")
                    
                    return Response({
                        'url': file_url,
                        'event_image_id': str(event_image.id),
                        'filename': filename,
                        'message': 'Image uploaded and associated with event successfully'
                    })
                    
                except Event.DoesNotExist:
                    # Clean up uploaded file if event not found
                    try:
                        default_storage.delete(saved_path)
                    except Exception as del_e:
                        print(f"[PUBLIC-UPLOAD] ⚠️ Could not delete file {saved_path}: {del_e}")
                    return Response({'detail': 'Event not found'}, status=status.HTTP_404_NOT_FOUND)
                except Exception as e:
                    # Clean up uploaded file on any error
                    try:
                        default_storage.delete(saved_path)
                    except Exception as del_e:
                        print(f"[PUBLIC-UPLOAD] ⚠️ Could not delete file {saved_path}: {del_e}")
                    print(f"[PUBLIC-UPLOAD] ❌ Error creating EventImage: {e}")
                    return Response({'detail': 'Error associating image with event'}, 
                                  status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # Return just the file URL if no event association
            # ✅ IMPORTANTE: También retornar el path para poder asociarlo después
            return Response({
                'url': file_url,
                'filename': filename,
                'file_path': saved_path,  # ✅ NUEVO: Path del archivo para asociarlo después
                'message': 'Image uploaded successfully'
            })
            
        except Exception as e:
            print(f"[PUBLIC-UPLOAD] ❌ Error uploading file: {e}")
            return Response({'detail': 'Error uploading file'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'])
    def active_forms(self, request):
        """
        🚀 PUBLIC ENDPOINT: Get active forms for public ticket purchases.
        No authentication required.
        """
        try:
            # Get form ID from query params
            form_id = request.query_params.get('form_id')
            
            if form_id:
                # Get specific form by ID
                try:
                    form = Form.objects.get(id=form_id, status='active')
                    serializer = FormSerializer(form)
                    return Response(serializer.data)
                except Form.DoesNotExist:
                    return Response({'detail': 'Form not found'}, status=status.HTTP_404_NOT_FOUND)
            else:
                # Get all active forms (for backward compatibility)
                active_forms = Form.objects.filter(status='active').order_by('-updated_at')
                serializer = FormSerializer(active_forms, many=True)
                return Response(serializer.data)
                
        except Exception as e:
            print(f"[PUBLIC-FORMS] ❌ Error fetching active forms: {e}")
            return Response({'detail': 'Error fetching forms'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# 🎫 COMPLIMENTARY: Public endpoints for complimentary ticket redemption

@api_view(['GET'])
@permission_classes([AllowAny])
def get_complimentary_invitation(request, public_token):
    """
    Get complimentary ticket invitation information (public endpoint).
    
    No authentication required. Returns event info and invitation details.
    If already redeemed, includes ticket information.
    """
    try:
        invitation = ComplimentaryTicketInvitation.objects.get(
            public_token=public_token
        )
        
        serializer = PublicComplimentaryTicketInvitationSerializer(invitation, context={'request': request})
        data = serializer.data
        data['status'] = invitation.status
        data['has_email'] = bool(invitation.email)
        
        # If redeemed, include ticket information
        if invitation.status == 'redeemed' and invitation.order:
            from apps.events.models import Ticket
            from .serializers import TicketSerializer
            # Tickets are related through OrderItem, not directly to Order
            tickets = Ticket.objects.filter(order_item__order=invitation.order).select_related(
                'order_item__ticket_tier'
            )
            if tickets.exists():
                ticket_serializer = TicketSerializer(tickets, many=True)
                data['tickets'] = ticket_serializer.data
                data['order_number'] = invitation.order.order_number
            else:
                data['tickets'] = []
                data['order_number'] = invitation.order.order_number
        else:
            data['tickets'] = []
            data['order_number'] = None
        
        return Response(data)
        
    except ComplimentaryTicketInvitation.DoesNotExist:
        return Response(
            {'detail': 'Invitation not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching invitation {public_token}: {e}", exc_info=True)
        return Response(
            {'detail': f'Error fetching invitation: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([AllowAny])
def redeem_complimentary_invitation(request, public_token):
    """
    Redeem a complimentary ticket invitation (public endpoint).
    
    No authentication required. Creates order, tickets, and QR codes.
    Email is optional - if not provided, no confirmation email will be sent.
    """
    try:
        invitation = ComplimentaryTicketInvitation.objects.get(
            public_token=public_token
        )
        
        if invitation.status != 'pending':
            return Response(
                {'detail': 'Invitation already redeemed or cancelled'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = ComplimentaryTicketInvitationRedeemSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        user_data = {
            'first_name': serializer.validated_data.get('first_name', ''),
            'last_name': serializer.validated_data.get('last_name', ''),
            'email': serializer.validated_data.get('email', ''),
        }
        ticket_quantity = serializer.validated_data['ticket_quantity']
        
        # Redeem invitation (creates order, tickets, QR codes)
        tickets = redeem_invitation(invitation, user_data, ticket_quantity)
        
        # Serialize tickets for response
        from .serializers import TicketSerializer
        ticket_serializer = TicketSerializer(tickets, many=True)
        
        return Response({
            'success': True,
            'invitation_id': str(invitation.id),
            'order_number': invitation.order.order_number if invitation.order else None,
            'tickets': ticket_serializer.data,
            'ticket_count': len(tickets),
            'email_sent': False,  # No email sent for complimentary tickets without email
        }, status=status.HTTP_201_CREATED)
        
    except ComplimentaryTicketInvitation.DoesNotExist:
        return Response(
            {'detail': 'Invitation not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except ValueError as e:
        return Response(
            {'detail': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error redeeming invitation {public_token}: {e}", exc_info=True)
        return Response(
            {'detail': 'Error redeeming invitation'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
