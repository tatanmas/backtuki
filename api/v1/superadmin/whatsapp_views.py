"""SuperAdmin WhatsApp views."""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from .permissions import IsSuperUser  # ENTERPRISE: Solo superusers autenticados
from rest_framework import status
from django.utils import timezone

from apps.whatsapp.models import (
    WhatsAppSession, WhatsAppReservationRequest, TourOperator,
    ExperienceOperatorBinding, WhatsAppMessage, WhatsAppChat,
    GroupOutreachConfig,
    GroupOutreachSent,
    WhatsAppReservationMessageConfig,
)
from apps.whatsapp.services.whatsapp_client import WhatsAppWebService
from apps.whatsapp.services.templates.defaults import DEFAULT_TEMPLATES
from apps.experiences.models import Experience
from apps.accommodations.models import Accommodation, Hotel, RentalHub


@api_view(['GET'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def whatsapp_status(request):
    """Get WhatsApp service status."""
    whatsapp_service = WhatsAppWebService()
    status_data = whatsapp_service.get_status()
    
    # Get or create session
    try:
        session = WhatsAppSession.objects.first()
        if not session:
            session = WhatsAppSession.objects.create(
                status='disconnected',
                created_at=timezone.now()
            )
        
        # Sync status from service if connected
        if status_data.get('isReady'):
            if session.status != 'connected':
                session.status = 'connected'
            if status_data.get('phone_number') and not session.phone_number:
                session.phone_number = status_data.get('phone_number', '')
            if status_data.get('number') and not session.name:
                session.name = status_data.get('number', '')
            session.save()
        elif status_data.get('hasQR') and session.status != 'qr_pending':
            session.status = 'qr_pending'
            session.save()
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception(f"Error syncing WhatsApp session: {e}")
        session = None
    
    return Response({
        'service_status': status_data,
        'session': {
            'id': str(session.id) if session else None,
            'status': session.status if session else 'disconnected',
            'phone_number': session.phone_number if session else '',
            'name': session.name if session else '',
            'last_seen': session.last_seen.isoformat() if session and session.last_seen else None,
            'qr_code': session.qr_code if session and session.status == 'qr_pending' else None
        } if session else {
            'id': None,
            'status': 'disconnected',
            'phone_number': '',
            'name': '',
            'last_seen': None,
            'qr_code': None
        }
    })


@api_view(['POST'])
@permission_classes([IsSuperUser])
def whatsapp_disconnect(request):
    """Desconectar sesión de WhatsApp para poder vincular otra cuenta."""
    try:
        service = WhatsAppWebService()
        ok = service.disconnect()
        if ok:
            session = WhatsAppSession.objects.first()
            if session:
                session.status = 'disconnected'
                session.phone_number = ''
                session.name = ''
                session.qr_code = ''
                session.save()
            return Response({'success': True, 'message': 'Sesión desconectada. Reinicia el servicio para mostrar el QR.'})
        return Response({'success': False, 'error': 'No se pudo desconectar'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception(f"Error disconnecting WhatsApp: {e}")
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def whatsapp_qr(request):
    """Get current QR code."""
    try:
        whatsapp_service = WhatsAppWebService()
        qr = whatsapp_service.get_qr_code()
        
        if qr:
            # Update session if table exists
            try:
                session = WhatsAppSession.objects.first()
                if not session:
                    session = WhatsAppSession.objects.create(
                        status='qr_pending',
                        created_at=timezone.now()
                    )
                session.qr_code = qr
                session.status = 'qr_pending'
                session.save()
            except Exception:
                # Table might not exist yet
                pass
            
            return Response({'qr': qr})
        else:
            # 200 con qr: null = "esperando QR" (ej. post-disconnect), no es error
            return Response({'qr': None})
    except Exception as e:
        return Response({'qr': None, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsSuperUser])
def whatsapp_request_new_qr(request):
    """Ask the WhatsApp service to re-initialize and emit a new QR (e.g. after disconnect / "Recargar")."""
    try:
        service = WhatsAppWebService()
        ok, err_msg = service.request_new_qr()
        if ok:
            return Response({'success': True, 'message': 'Solicitado nuevo QR; en unos segundos vuelve a cargar.'})
        # 503 cuando el servicio falla (ruta no encontrada, perfil bloqueado, etc.); 502 solo si no hay mensaje
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE if err_msg else status.HTTP_502_BAD_GATEWAY
        return Response({'success': False, 'error': err_msg or 'No se pudo solicitar nuevo QR'}, status=status_code)
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error requesting new QR: %s", e)
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def whatsapp_reservations(request):
    """List WhatsApp reservations - robust implementation that handles schema mismatches."""
    import logging
    from django.db import connection
    
    logger = logging.getLogger(__name__)
    status_filter = request.query_params.get('status')
    operator_id = request.query_params.get('operator_id')
    
    try:
        # Use raw SQL since the schema doesn't match the model exactly
        # The table has: num_passengers, customer_phone, whatsapp_message_id (VARCHAR)
        # The model expects: passengers, whatsapp_message (FK), etc.
        
        query = """
            SELECT 
                wr.id, 
                wr.tour_code, 
                wr.status, 
                wr.created_at, 
                wr.timeout_at,
                wr.operator_id, 
                wr.experience_id,
                wr.passengers,
                wr.confirmation_token,
                wm.phone as customer_phone
            FROM whatsapp_whatsappreservationrequest wr
            LEFT JOIN whatsapp_whatsappmessage wm ON wr.whatsapp_message_id = wm.id
            WHERE 1=1
        """
        params = []
        
        if status_filter:
            query += " AND status = %s"
            params.append(status_filter)
        
        if operator_id:
            query += " AND operator_id = %s"
            params.append(operator_id)
        
        query += " ORDER BY created_at DESC LIMIT 50"
        
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            columns = [col[0] for col in cursor.description]
            rows = cursor.fetchall()
        
        reservations = []
        for row in rows:
            row_dict = dict(zip(columns, row))
            
            # Get operator data safely
            operator_data = None
            operator_id_val = row_dict.get('operator_id')
            if operator_id_val:
                try:
                    operator = TourOperator.objects.get(id=operator_id_val)
                    operator_data = {
                        'id': str(operator.id),
                        'name': operator.name
                    }
                except (TourOperator.DoesNotExist, Exception) as e:
                    logger.debug(f"Could not fetch operator {operator_id_val}: {e}")
            
            # Get experience data safely
            experience_data = None
            experience_id_val = row_dict.get('experience_id')
            if experience_id_val:
                try:
                    experience = Experience.objects.get(id=experience_id_val)
                    experience_data = {
                        'id': str(experience.id),
                        'title': experience.title
                    }
                except (Experience.DoesNotExist, Exception) as e:
                    logger.debug(f"Could not fetch experience {experience_id_val}: {e}")
            
            # Format dates safely
            created_at = row_dict.get('created_at')
            timeout_at = row_dict.get('timeout_at')
            
            created_at_str = None
            if created_at:
                try:
                    created_at_str = created_at.isoformat() if hasattr(created_at, 'isoformat') else str(created_at)
                except Exception:
                    created_at_str = str(created_at)
            
            timeout_at_str = None
            if timeout_at:
                try:
                    timeout_at_str = timeout_at.isoformat() if hasattr(timeout_at, 'isoformat') else str(timeout_at)
                except Exception:
                    timeout_at_str = str(timeout_at)
            
            reservations.append({
                'id': str(row_dict.get('id', '')),
                'tour_code': row_dict.get('tour_code', ''),
                'passengers': row_dict.get('passengers'),
                'status': row_dict.get('status', ''),
                'operator': operator_data,
                'experience': experience_data,
                'customer_phone': row_dict.get('customer_phone'),
                'created_at': created_at_str,
                'timeout_at': timeout_at_str
            })
        
        return Response({'reservations': reservations})
    
    except Exception as e:
        logger.exception(f"Error fetching reservations: {e}")
        # Always return a valid response to avoid breaking the UI
        return Response({'reservations': []})


@api_view(['GET'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def whatsapp_operators(request):
    """List tour operators - includes auto-created operators from organizers."""
    import logging
    from apps.organizers.models import Organizer
    
    logger = logging.getLogger(__name__)
    
    try:
        # Obtener todos los operadores (manuales + auto-creados)
        operators = TourOperator.objects.filter(is_active=True).select_related(
            'organizer', 'default_whatsapp_group'
        ).order_by('name')
        
        # También incluir organizadores que no tienen operador pero tienen experiencias
        organizers_with_experiences = Organizer.objects.filter(
            has_experience_module=True,
            experiences__isnull=False
        ).distinct().prefetch_related('tour_operators')
        
        result = []
        
        # Procesar operadores existentes
        for operator in operators:
            try:
                # Safely get whatsapp_number (may not exist in old schema)
                whatsapp_number = ''
                if hasattr(operator, 'whatsapp_number'):
                    whatsapp_number = operator.whatsapp_number or ''
                
                # Safely get contact info
                contact_phone = operator.contact_phone if hasattr(operator, 'contact_phone') else ''
                contact_email = operator.contact_email if hasattr(operator, 'contact_email') else ''
                
                # Safely count experiences
                experiences_count = 0
                try:
                    if hasattr(operator, 'experience_bindings'):
                        experiences_count = operator.experience_bindings.filter(is_active=True).count()
                except Exception:
                    pass
                
                # Get organizer info if linked
                organizer_data = None
                if operator.organizer:
                    organizer_data = {
                        'id': str(operator.organizer.id),
                        'name': operator.organizer.name,
                        'slug': operator.organizer.slug
                    }
                
                # Get default WhatsApp group info if set
                default_group_data = None
                if operator.default_whatsapp_group:
                    default_group_data = {
                        'id': str(operator.default_whatsapp_group.id),
                        'chat_id': operator.default_whatsapp_group.chat_id,
                        'name': operator.default_whatsapp_group.name
                    }
                
                result.append({
                    'id': str(operator.id),
                    'name': operator.name,
                    'whatsapp_number': whatsapp_number,
                    'contact_phone': contact_phone,
                    'contact_email': contact_email,
                    'experiences_count': experiences_count,
                    'organizer': organizer_data,
                    'default_whatsapp_group': default_group_data,
                    'is_system_created': operator.is_system_created if hasattr(operator, 'is_system_created') else False
                })
            except Exception as e:
                logger.warning(f"Error processing operator {operator.id}: {e}")
                # Skip this operator but continue with others
                continue
        
        # Agregar organizadores sin operador (para mostrar que pueden crear uno)
        organizers_without_operator = []
        for organizer in organizers_with_experiences:
            # Verificar si ya tiene un operador
            has_operator = organizer.tour_operators.filter(is_active=True).exists()
            if not has_operator:
                experiences_count = organizer.experiences.count()
                organizers_without_operator.append({
                    'id': None,  # No tiene operador aún
                    'name': organizer.name,
                    'organizer': {
                        'id': str(organizer.id),
                        'name': organizer.name,
                        'slug': organizer.slug
                    },
                    'experiences_count': experiences_count,
                    'is_system_created': False,
                    'needs_operator_creation': True  # Flag para indicar que necesita crear operador
                })
        
        # Agregar organizadores sin operador al final
        result.extend(organizers_without_operator)
        
        return Response({
            'operators': result,
            'total': len(result),
            'organizers_without_operator': len(organizers_without_operator)
        })
    except Exception as e:
        logger.exception(f"Error fetching operators: {e}")
        return Response({'operators': [], 'total': 0, 'organizers_without_operator': 0})


@api_view(['POST'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def whatsapp_bind_experience_operator(request):
    """Bind experience to operator."""
    experience_id = request.data.get('experience_id')
    operator_id = request.data.get('operator_id')
    priority = request.data.get('priority', 0)
    
    try:
        experience = Experience.objects.get(id=experience_id)
        operator = TourOperator.objects.get(id=operator_id)
        
        binding, created = ExperienceOperatorBinding.objects.get_or_create(
            experience=experience,
            tour_operator=operator,
            defaults={'priority': priority, 'is_active': True}
        )
        
        if not created:
            binding.priority = priority
            binding.is_active = True
            binding.save()
        
        return Response({
            'success': True,
            'binding_id': str(binding.id),
            'created': created
        })
    except Experience.DoesNotExist:
        return Response({'error': 'Experience not found'}, status=status.HTTP_404_NOT_FOUND)
    except TourOperator.DoesNotExist:
        return Response({'error': 'Operator not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def whatsapp_messages(request):
    """List WhatsApp messages with filters."""
    import logging
    from django.db import connection
    
    logger = logging.getLogger(__name__)
    chat_id = request.query_params.get('chat_id')
    sync = request.query_params.get('sync', '').lower() in ('1', 'true', 'yes')
    is_reservation_related = request.query_params.get('is_reservation_related')
    has_code = request.query_params.get('has_code')
    date_from = request.query_params.get('date_from')
    date_to = request.query_params.get('date_to')
    
    try:
        if chat_id and sync:
            try:
                from apps.whatsapp.services.sync_service import WhatsAppSyncService
                sync_service = WhatsAppSyncService()
                sync_service.sync_chat_messages(chat_id)
            except Exception as sync_err:
                logger.warning(f"Sync chat messages failed (continuing with DB): {sync_err}")
        
        # Construir queryset de forma robusta
        # Evitar select_related con linked_reservation_request para evitar error de confirmation_token
        queryset = WhatsAppMessage.objects.select_related('chat')
        
        if chat_id:
            queryset = queryset.filter(chat__chat_id=chat_id)
        
        if is_reservation_related is not None:
            is_related = is_reservation_related.lower() == 'true'
            queryset = queryset.filter(is_reservation_related=is_related)
        
        if has_code is not None:
            has_code_bool = has_code.lower() == 'true'
            if has_code_bool:
                queryset = queryset.exclude(reservation_code__isnull=True).exclude(reservation_code='')
            else:
                queryset = queryset.filter(reservation_code__isnull=True) | queryset.filter(reservation_code='')
        
        if date_from:
            queryset = queryset.filter(timestamp__gte=date_from)
        
        if date_to:
            queryset = queryset.filter(timestamp__lte=date_to)
        
        messages = []
        # Tomar los 100 más recientes, luego ordenar cronológicamente para mostrar
        recent = list(queryset.order_by('-timestamp')[:100])
        for msg in reversed(recent):
            # Obtener datos de forma segura
            chat_data = None
            try:
                if msg.chat:
                    chat_data = {
                        'id': str(msg.chat.id),
                        'name': msg.chat.name,
                        'type': msg.chat.type
                    }
            except Exception:
                pass
            
            # Obtener metadata de forma segura (para sender_name en grupos)
            message_metadata = {}
            try:
                if hasattr(msg, 'metadata') and msg.metadata and isinstance(msg.metadata, dict):
                    message_metadata = msg.metadata
            except Exception:
                pass
            
            linked_reservation_request_id = None
            try:
                # Obtener el ID directamente desde el campo ForeignKey sin cargar el objeto
                if hasattr(msg, 'linked_reservation_request_id') and msg.linked_reservation_request_id:
                    linked_reservation_request_id = str(msg.linked_reservation_request_id)
            except Exception:
                pass
            
            # Obtener is_automated de forma segura
            is_automated = False
            try:
                is_automated = getattr(msg, 'is_automated', False)
            except Exception:
                pass
            
            # Asegurar que siempre haya un timestamp válido
            timestamp_value = None
            if msg.timestamp:
                timestamp_value = msg.timestamp.isoformat()
            elif hasattr(msg, 'created_at') and msg.created_at:
                # Fallback a created_at si timestamp no está disponible
                timestamp_value = msg.created_at.isoformat()
                logger.warning(f"⚠️ Message {msg.id} using created_at as timestamp: {timestamp_value}")
            else:
                # Último fallback: usar timezone.now() (ya importado al inicio)
                timestamp_value = timezone.now().isoformat()
                logger.warning(f"⚠️ Message {msg.id} using now() as timestamp: {timestamp_value}")
            
            # Enterprise: media_type, reply_to (safe getattr for migration rollback)
            media_type = getattr(msg, 'media_type', None)
            reply_to_whatsapp_id = getattr(msg, 'reply_to_whatsapp_id', None)
            messages.append({
                'id': str(msg.id),
                'whatsapp_id': msg.whatsapp_id,
                'phone': msg.phone,
                'type': msg.type,
                'content': msg.content[:200] if msg.content else '',
                'full_content': msg.content or '',
                'timestamp': timestamp_value,
                'processed': msg.processed,
                'chat': chat_data,
                'reservation_code': msg.reservation_code,
                'is_reservation_related': msg.is_reservation_related,
                'linked_reservation_request_id': linked_reservation_request_id,
                'is_automated': is_automated,
                'metadata': message_metadata,
                'media_type': media_type,
                'reply_to_whatsapp_id': reply_to_whatsapp_id,
            })
        
        return Response({'messages': messages})
    except Exception as e:
        logger.exception(f"Error fetching messages: {e}")
        return Response({'messages': []})


@api_view(['PATCH'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def whatsapp_mark_message_reservation(request, message_id):
    """Mark/unmark message as reservation related."""
    try:
        message = WhatsAppMessage.objects.get(id=message_id)
        is_reservation_related = request.data.get('is_reservation_related')
        
        if is_reservation_related is None:
            return Response({'error': 'is_reservation_related is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        message.is_reservation_related = bool(is_reservation_related)
        message.save()
        
        return Response({
            'success': True,
            'message_id': str(message.id),
            'is_reservation_related': message.is_reservation_related
        })
    except WhatsAppMessage.DoesNotExist:
        return Response({'error': 'Message not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception(f"Error marking message: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def whatsapp_chats(request):
    """List all WhatsApp chats/groups."""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        from django.db.models import Count
        
        # Sincronizar chats desde Node.js (puede fallar con 503 si servicio no listo)
        try:
            from apps.whatsapp.services.sync_service import WhatsAppSyncService
            sync_service = WhatsAppSyncService()
            sync_result = sync_service.sync_all_chats()
            logger.info(f"Chats sync: {sync_result['created']} created, {sync_result['updated']} updated")
        except Exception as sync_error:
            # 503/connection errors: usar solo DB sin fallar
            logger.warning(f"Chat sync skipped (service unavailable): {sync_error}")
        
        chats = WhatsAppChat.objects.select_related('assigned_operator').annotate(
            message_count=Count('messages')
        )
        
        # Filtrar por tags si se proporciona
        tags_filter = request.query_params.get('tags')
        if tags_filter:
            # tags_filter puede ser una lista separada por comas
            tags_list = [tag.strip() for tag in tags_filter.split(',')]
            # Filtrar chats que tengan al menos uno de los tags
            chats = chats.filter(tags__overlap=tags_list)
        
        result = []
        # Ordenar por last_message_at descendente (más recientes primero)
        try:
            ordered_chats = chats.order_by('-last_message_at', '-created_at')
        except Exception:
            ordered_chats = chats.order_by('-created_at')
        
        for chat in ordered_chats:
            # Obtener tags de forma segura
            tags = []
            try:
                if chat.tags and isinstance(chat.tags, list):
                    tags = chat.tags
            except Exception:
                pass
            
            chat_data = {
                'id': str(chat.id),
                'chat_id': chat.chat_id,
                'name': chat.name or chat.chat_id,  # Fallback a chat_id si name está vacío
                'nickname': chat.nickname or '',
                'whatsapp_name': chat.whatsapp_name or '',
                'profile_picture_url': chat.profile_picture_url or '',
                'type': chat.type,
                'assigned_operator': {
                    'id': str(chat.assigned_operator.id),
                    'name': chat.assigned_operator.name
                } if chat.assigned_operator else None,
                'is_active': chat.is_active,
                'last_message_at': chat.last_message_at.isoformat() if chat.last_message_at else None,
                'last_message_preview': getattr(chat, 'last_message_preview', '') or '',
                'message_count': getattr(chat, 'message_count', 0),
                'unread_count': chat.unread_count or 0,
                'tags': tags
            }
            
            # Agregar información específica de grupos
            if chat.type == 'group':
                participants = []
                try:
                    if chat.participants and isinstance(chat.participants, list):
                        participants = chat.participants
                except Exception:
                    pass
                chat_data['participants'] = participants
                chat_data['participants_count'] = len(participants)
                chat_data['group_description'] = chat.group_description or ''
            
            result.append(chat_data)
        
        return Response({'chats': result})
    except Exception as e:
        logger.exception(f"Error fetching chats: {e}")
        return Response({'chats': []})


@api_view(['GET'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def whatsapp_profile_picture(request, chat_id):
    """
    Proxy for WhatsApp profile pictures. Fetches from Node.js service to avoid CORS
    and URL expiration. Returns image binary.
    chat_id: WhatsApp chat_id (e.g. 56912345678@c.us or 120363...@g.us)
    """
    import logging
    from django.http import HttpResponse

    logger = logging.getLogger(__name__)
    try:
        whatsapp_service = WhatsAppWebService()
        url = f"{whatsapp_service.base_url}/api/profile-picture/{chat_id}"
        resp = whatsapp_service._get_raw(url)
        if resp is None or resp.status_code != 200:
            return Response(
                {'error': 'No se pudo obtener la foto de perfil'},
                status=status.HTTP_502_BAD_GATEWAY
            )
        content_type = resp.headers.get('Content-Type', 'image/jpeg')
        return HttpResponse(
            resp.content,
            content_type=content_type,
            headers={'Cache-Control': 'private, max-age=300'}
        )
    except Exception as e:
        logger.exception(f"Error proxying profile picture for {chat_id}: {e}")
        return Response(
            {'error': 'Error al obtener foto de perfil'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def whatsapp_chat_info(request, chat_id):
    """Get complete information about a specific chat."""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        chat = WhatsAppChat.objects.select_related('assigned_operator').get(id=chat_id)
        
        # Obtener tags de forma segura
        tags = []
        try:
            if chat.tags and isinstance(chat.tags, list):
                tags = chat.tags
        except Exception:
            pass
        
        chat_info = {
            'id': str(chat.id),
            'chat_id': chat.chat_id,
            'name': chat.name or chat.chat_id,
            'nickname': chat.nickname or '',
            'whatsapp_name': chat.whatsapp_name or '',
            'profile_picture_url': chat.profile_picture_url or '',
            'type': chat.type,
            'notes': chat.notes or '',
            'tags': tags,
            'unread_count': chat.unread_count or 0,
            'assigned_operator': {
                'id': str(chat.assigned_operator.id),
                'name': chat.assigned_operator.name
            } if chat.assigned_operator else None,
            'is_active': chat.is_active,
            'last_message_at': chat.last_message_at.isoformat() if chat.last_message_at else None,
            'last_message_preview': getattr(chat, 'last_message_preview', '') or '',
            'created_at': chat.created_at.isoformat() if chat.created_at else None
        }
        
        # Agregar información específica de grupos
        if chat.type == 'group':
            participants = []
            try:
                if chat.participants and isinstance(chat.participants, list):
                    participants = chat.participants
            except Exception:
                pass
            chat_info['participants'] = participants
            chat_info['participants_count'] = len(participants)
            chat_info['group_description'] = chat.group_description or ''
        
        return Response(chat_info)
    except WhatsAppChat.DoesNotExist:
        return Response({'error': 'Chat not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.exception(f"Error fetching chat info: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PATCH'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def whatsapp_update_chat(request, chat_id):
    """Update chat information (nickname, notes, tags)."""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        chat = WhatsAppChat.objects.get(id=chat_id)
        
        # Actualizar campos permitidos
        if 'nickname' in request.data:
            chat.nickname = request.data.get('nickname', '').strip()
        
        if 'notes' in request.data:
            chat.notes = request.data.get('notes', '').strip()
        
        if 'tags' in request.data:
            tags = request.data.get('tags', [])
            # Validar que tags sea una lista
            if isinstance(tags, list):
                # Limpiar tags (remover espacios, convertir a string)
                cleaned_tags = [str(tag).strip() for tag in tags if tag and str(tag).strip()]
                chat.tags = cleaned_tags
            else:
                return Response({'error': 'tags must be a list'}, status=status.HTTP_400_BAD_REQUEST)
        
        chat.save()
        
        # Obtener tags de forma segura para la respuesta
        tags = []
        try:
            if chat.tags and isinstance(chat.tags, list):
                tags = chat.tags
        except Exception:
            pass
        
        return Response({
            'id': str(chat.id),
            'nickname': chat.nickname or '',
            'notes': chat.notes or '',
            'tags': tags
        })
    except WhatsAppChat.DoesNotExist:
        return Response({'error': 'Chat not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.exception(f"Error updating chat: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def whatsapp_mark_chat_read(request, chat_id):
    """Mark chat as read (reset unread_count)."""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        chat = WhatsAppChat.objects.get(id=chat_id)
        chat.unread_count = 0
        chat.save()
        
        return Response({
            'success': True,
            'unread_count': 0
        })
    except WhatsAppChat.DoesNotExist:
        return Response({'error': 'Chat not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.exception(f"Error marking chat as read: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PATCH'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def whatsapp_assign_chat_operator(request, chat_id):
    """Assign chat/group to operator."""
    try:
        chat = WhatsAppChat.objects.get(id=chat_id)
        operator_id = request.data.get('operator_id')
        
        if operator_id:
            operator = TourOperator.objects.get(id=operator_id)
            chat.assigned_operator = operator
        else:
            chat.assigned_operator = None
        
        chat.save()
        
        return Response({
            'success': True,
            'chat_id': str(chat.id),
            'assigned_operator': {
                'id': str(chat.assigned_operator.id),
                'name': chat.assigned_operator.name
            } if chat.assigned_operator else None
        })
    except WhatsAppChat.DoesNotExist:
        return Response({'error': 'Chat not found'}, status=status.HTTP_404_NOT_FOUND)
    except TourOperator.DoesNotExist:
        return Response({'error': 'Operator not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception(f"Error assigning chat: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def whatsapp_sync_chats(request):
    """Synchronize WhatsApp chats from Node.js service."""
    import logging
    from django.core.management import call_command
    from io import StringIO
    
    logger = logging.getLogger(__name__)
    
    try:
        # Llamar al comando de sincronización
        out = StringIO()
        call_command('sync_whatsapp_chats', stdout=out, stderr=out)
        output = out.getvalue()
        
        # Obtener chats actualizados
        chats = WhatsAppChat.objects.select_related('assigned_operator').all()
        from django.db.models import Count
        chats = chats.annotate(message_count=Count('messages'))
        
        result = []
        for chat in chats.order_by('-last_message_at'):
            result.append({
                'id': str(chat.id),
                'chat_id': chat.chat_id,
                'name': chat.name,
                'type': chat.type,
                'assigned_operator': {
                    'id': str(chat.assigned_operator.id),
                    'name': chat.assigned_operator.name
                } if chat.assigned_operator else None,
                'is_active': chat.is_active,
                'last_message_at': chat.last_message_at.isoformat() if chat.last_message_at else None,
                'message_count': chat.message_count
            })
        
        return Response({
            'success': True,
            'chats': result,
            'sync_output': output
        })
    except Exception as e:
        logger.exception(f"Error syncing chats: {e}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def whatsapp_send_message(request):
    """Send a WhatsApp message from SuperAdmin panel."""
    import logging
    from apps.whatsapp.services.whatsapp_client import WhatsAppWebService
    from apps.whatsapp.models import WhatsAppMessage, WhatsAppChat
    from django.utils import timezone
    
    logger = logging.getLogger(__name__)
    
    try:
        chat_id = request.data.get('chat_id')
        phone = request.data.get('phone')
        text = request.data.get('text')
        is_group = request.data.get('is_group', False)
        
        if not chat_id or not text:
            return Response({
                'success': False,
                'error': 'chat_id and text are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Enviar mensaje a través del servicio WhatsApp
        whatsapp_service = WhatsAppWebService()
        
        if is_group:
            result = whatsapp_service.send_message(phone, text, group_id=chat_id)
        else:
            clean_phone = WhatsAppWebService.clean_phone_number(phone)
            result = whatsapp_service.send_message(clean_phone, text, chat_id=chat_id)
        
        # Guardar mensaje en la base de datos
        try:
            chat = WhatsAppChat.objects.get(chat_id=chat_id)
        except WhatsAppChat.DoesNotExist:
            # Si no existe el chat, crearlo
            chat = WhatsAppChat.objects.create(
                chat_id=chat_id,
                name=phone,
                type='group' if is_group else 'individual',
                is_active=True
            )
        
        # Crear registro del mensaje saliente (enviado manualmente, no automatizado)
        message = WhatsAppMessage.objects.create(
            whatsapp_id=f"out_{timezone.now().timestamp()}",
            phone=phone,
            type='out',
            content=text,
            timestamp=timezone.now(),
            processed=True,
            chat=chat,
            is_automated=False  # Mensaje enviado manualmente desde SuperAdmin
        )
        
        # Actualizar último mensaje del chat
        chat.last_message_at = timezone.now()
        chat.save()
        
        return Response({
            'success': True,
            'message_id': str(message.id),
            'message': {
                'id': str(message.id),
                'type': 'out',
                'content': text,
                'timestamp': message.timestamp.isoformat()
            }
        })
        
    except Exception as e:
        logger.exception(f"Error sending WhatsApp message: {e}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def whatsapp_groups(request):
    """List all WhatsApp groups."""
    import logging
    from django.db.models import Count
    
    logger = logging.getLogger(__name__)
    
    try:
        # Filtrar solo grupos
        groups = WhatsAppChat.objects.filter(type='group').select_related('assigned_operator').annotate(
            message_count=Count('messages')
        )
        
        # Siempre sincronizar grupos desde Node.js para mantener información actualizada
        try:
            from apps.whatsapp.services.sync_service import WhatsAppSyncService
            
            sync_service = WhatsAppSyncService()
            sync_result = sync_service.sync_all_groups()
            logger.info(f"Groups sync: {sync_result['created']} created, {sync_result['updated']} updated")
        except Exception as sync_error:
            logger.error(f"Error syncing groups from Node.js service: {sync_error}", exc_info=True)
            # Continuar con grupos existentes
        
        # Re-fetch grupos después de la sincronización
        groups = WhatsAppChat.objects.filter(type='group').select_related('assigned_operator').annotate(
            message_count=Count('messages')
        )
        logger.info(f"Total groups in database: {groups.count()}")
        
        # Filtrar por operador asignado si se proporciona
        operator_id = request.query_params.get('operator_id')
        if operator_id:
            groups = groups.filter(assigned_operator_id=operator_id)
        
        result = []
        # Ordenar por last_message_at descendente (más recientes primero)
        try:
            ordered_groups = list(groups.order_by('-last_message_at', '-created_at'))
        except Exception:
            ordered_groups = list(groups.order_by('-created_at'))

        # Conteo de participantes desde outreach cache cuando exista (evita mostrar siempre 0)
        from apps.whatsapp.models import GroupOutreachConfig
        outreach_counts = dict(
            GroupOutreachConfig.objects.filter(
                group__in=ordered_groups,
                cached_participants_total__isnull=False
            ).values_list('group_id', 'cached_participants_total')
        )
        
        for group in ordered_groups:
            # Obtener participantes de forma segura
            participants = []
            try:
                if group.participants and isinstance(group.participants, list):
                    participants = group.participants
            except Exception:
                pass

            # Usar cache de outreach si existe; si no, len(participants) (suele ser 0 si Node no devuelve participantes)
            participants_count = outreach_counts.get(group.id)
            if participants_count is None:
                participants_count = len(participants)
            
            # Obtener tags de forma segura
            tags = []
            try:
                if group.tags and isinstance(group.tags, list):
                    tags = group.tags
            except Exception:
                pass
            
            result.append({
                'id': str(group.id),
                'chat_id': group.chat_id,
                'name': group.name or group.chat_id,
                'nickname': group.nickname or '',
                'profile_picture_url': group.profile_picture_url or '',
                'description': group.group_description or '',
                'participants': participants,
                'participants_count': participants_count,
                'assigned_operator': {
                    'id': str(group.assigned_operator.id),
                    'name': group.assigned_operator.name
                } if group.assigned_operator else None,
                'is_active': group.is_active,
                'last_message_at': group.last_message_at.isoformat() if group.last_message_at else None,
                'message_count': getattr(group, 'message_count', 0),
                'unread_count': group.unread_count or 0,
                'tags': tags
            })
        
        return Response({'groups': result})
    except Exception as e:
        logger.exception(f"Error fetching groups: {e}")
        return Response({'groups': []})


@api_view(['GET'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def whatsapp_group_info(request, group_id):
    """Get detailed information about a specific group."""
    import logging
    from apps.whatsapp.services.whatsapp_client import WhatsAppWebService
    
    logger = logging.getLogger(__name__)
    
    try:
        # Obtener grupo de la base de datos
        group = WhatsAppChat.objects.select_related('assigned_operator').get(id=group_id)
        
        if group.type != 'group':
            return Response({'error': 'Chat is not a group'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Obtener información actualizada del servicio Node.js
        whatsapp_service = WhatsAppWebService()
        try:
            node_info = whatsapp_service.get_group_info(group.chat_id)
            
            # Sincronizar información si está disponible
            if node_info:
                if node_info.get('participants'):
                    group.participants = node_info['participants']
                if node_info.get('description'):
                    group.group_description = node_info['description']
                if node_info.get('profile_picture_url'):
                    group.profile_picture_url = node_info['profile_picture_url']
                if node_info.get('name') and node_info['name'] != group.name:
                    group.name = node_info['name']
                group.save()
        except Exception as e:
            logger.warning(f"Could not sync group info from Node.js: {e}")
            # Continuar con información de la base de datos
        
        # Obtener participantes de forma segura
        participants = []
        try:
            if group.participants and isinstance(group.participants, list):
                participants = group.participants
        except Exception:
            pass
        
        # Obtener tags de forma segura
        tags = []
        try:
            if group.tags and isinstance(group.tags, list):
                tags = group.tags
        except Exception:
            pass
        
        return Response({
            'id': str(group.id),
            'chat_id': group.chat_id,
            'name': group.name or group.chat_id,
            'nickname': group.nickname or '',
            'profile_picture_url': group.profile_picture_url or '',
            'description': group.group_description or '',
            'participants': participants,
            'participants_count': len(participants),
            'assigned_operator': {
                'id': str(group.assigned_operator.id),
                'name': group.assigned_operator.name
            } if group.assigned_operator else None,
            'is_active': group.is_active,
            'last_message_at': group.last_message_at.isoformat() if group.last_message_at else None,
            'message_count': WhatsAppMessage.objects.filter(chat=group).count(),
            'unread_count': group.unread_count or 0,
            'tags': tags,
            'created_at': group.created_at.isoformat() if group.created_at else None
        })
    except WhatsAppChat.DoesNotExist:
        return Response({'error': 'Group not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.exception(f"Error fetching group info: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PATCH'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def whatsapp_assign_group_operator(request, group_id):
    """Assign an operator to a WhatsApp group."""
    import logging
    from apps.whatsapp.models import TourOperator
    
    logger = logging.getLogger(__name__)
    
    try:
        group = WhatsAppChat.objects.get(id=group_id)
        
        if group.type != 'group':
            return Response({'error': 'Chat is not a group'}, status=status.HTTP_400_BAD_REQUEST)
        
        operator_id = request.data.get('operator_id')
        
        if operator_id:
            try:
                operator = TourOperator.objects.get(id=operator_id)
                group.assigned_operator = operator
            except TourOperator.DoesNotExist:
                return Response({'error': 'Operator not found'}, status=status.HTTP_404_NOT_FOUND)
        else:
            # Si operator_id es null, desasignar
            group.assigned_operator = None
        
        group.save()
        
        return Response({
            'success': True,
            'group_id': str(group.id),
            'assigned_operator': {
                'id': str(group.assigned_operator.id),
                'name': group.assigned_operator.name
            } if group.assigned_operator else None
        })
    except WhatsAppChat.DoesNotExist:
        return Response({'error': 'Group not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.exception(f"Error assigning operator to group: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET', 'PATCH'])
@permission_classes([IsSuperUser])
def whatsapp_group_outreach(request, group_id):
    """
    GET: Return outreach config for group (create default if missing). Includes sent_count.
         Query param ?refresh=1 fetches participants from Node and returns eligible_count.
    PATCH: Update outreach config (enabled, message_templates, exclude_numbers, delays, etc.).
    """
    import logging
    from apps.whatsapp.services.whatsapp_client import WhatsAppWebService
    from apps.whatsapp.services.group_outreach_service import get_eligible_participants, _participant_phone_normalized

    logger = logging.getLogger(__name__)

    try:
        group = WhatsAppChat.objects.get(id=group_id)
    except WhatsAppChat.DoesNotExist:
        return Response({'error': 'Group not found'}, status=status.HTTP_404_NOT_FOUND)

    if group.type != 'group':
        return Response({'error': 'Chat is not a group'}, status=status.HTTP_400_BAD_REQUEST)

    if request.method == 'GET':
        config, _ = GroupOutreachConfig.objects.get_or_create(
            group=group,
            defaults={
                'enabled': False,
                'message_templates': [],
                'exclude_numbers': [],
                'min_delay_seconds': 120,
                'max_delay_seconds': 300,
                'max_per_run': 1,
                'skip_saved_contacts': True,
            }
        )
        sent_count = GroupOutreachSent.objects.filter(config=config).count()

        # Lista persistente de envíos (últimos 200) para mostrar en la UI
        sent_list = list(
            GroupOutreachSent.objects.filter(config=config)
            .order_by('-sent_at')
            .values('participant_id', 'phone_normalized', 'sent_at', 'message_used', 'message_index')[:200]
        )
        for s in sent_list:
            s['sent_at'] = s['sent_at'].isoformat() if s.get('sent_at') else None

        payload = {
            'id': str(config.id),
            'group_id': str(group.id),
            'group_name': group.name,
            'enabled': config.enabled,
            'message_templates': config.message_templates or [],
            'exclude_numbers': config.exclude_numbers or [],
            'min_delay_seconds': config.min_delay_seconds,
            'max_delay_seconds': config.max_delay_seconds,
            'max_per_run': config.max_per_run,
            'skip_saved_contacts': config.skip_saved_contacts,
            'last_run_at': config.last_run_at.isoformat() if config.last_run_at else None,
            'sent_count': sent_count,
            'eligible_count': config.cached_eligible_count,
            'eligible_count_cached_at': config.cached_eligible_at.isoformat() if config.cached_eligible_at else None,
            'participants_total': config.cached_participants_total,
            'sent_list': sent_list,
        }

        if request.query_params.get('refresh'):
            try:
                service = WhatsAppWebService()
                group_info = service.get_group_info(group.chat_id)
                saved_map = {}
                if config.skip_saved_contacts and group_info.get('participants'):
                    ids = [p.get('id') for p in group_info['participants'] if p.get('id')]
                    saved_map = service.check_saved_contacts(ids)
                eligible = get_eligible_participants(config, group_info, saved_map)
                count = len(eligible)
                total = len(group_info.get('participants') or [])
                config.cached_eligible_count = count
                config.cached_eligible_at = timezone.now()
                config.cached_participants_total = total
                config.cached_eligible_participants = [
                    {'id': p.get('id'), 'phone_normalized': _participant_phone_normalized(p)}
                    for p in eligible
                ]
                config.save(update_fields=[
                    'cached_eligible_count', 'cached_eligible_at', 'cached_participants_total',
                    'cached_eligible_participants',
                ])
                payload['eligible_count'] = count
                payload['eligible_count_cached_at'] = config.cached_eligible_at.isoformat()
                payload['participants_total'] = total
            except Exception as e:
                logger.warning(f"Refresh eligible count failed: {e}")
                payload['eligible_count'] = getattr(config, 'cached_eligible_count', None)
                payload['eligible_count_cached_at'] = config.cached_eligible_at.isoformat() if config.cached_eligible_at else None
                payload['participants_total'] = getattr(config, 'cached_participants_total', None)

        return Response(payload)

    # PATCH
    config = GroupOutreachConfig.objects.filter(group=group).first()
    if not config:
        config = GroupOutreachConfig.objects.create(
            group=group,
            enabled=False,
            message_templates=[],
            exclude_numbers=[],
        )

    data = request.data
    if 'enabled' in data:
        config.enabled = bool(data['enabled'])
    if 'message_templates' in data:
        config.message_templates = data['message_templates'] if isinstance(data['message_templates'], list) else []
    if 'exclude_numbers' in data:
        config.exclude_numbers = data['exclude_numbers'] if isinstance(data['exclude_numbers'], list) else []
    if 'min_delay_seconds' in data:
        config.min_delay_seconds = max(60, int(data.get('min_delay_seconds', 120)))
    if 'max_delay_seconds' in data:
        config.max_delay_seconds = max(config.min_delay_seconds, int(data.get('max_delay_seconds', 300)))
    if 'max_per_run' in data:
        config.max_per_run = max(1, min(5, int(data.get('max_per_run', 1))))
    if 'skip_saved_contacts' in data:
        config.skip_saved_contacts = bool(data['skip_saved_contacts'])
    # Invalidate eligible cache when filters change so next refresh recalculates
    if 'message_templates' in data or 'exclude_numbers' in data or 'skip_saved_contacts' in data:
        if config.cached_eligible_count is not None:
            config.cached_eligible_count = None
            config.cached_eligible_at = None
            config.cached_participants_total = None
            config.cached_eligible_participants = []
    config.save()

    sent_count = GroupOutreachSent.objects.filter(config=config).count()
    sent_list = list(
        GroupOutreachSent.objects.filter(config=config)
        .order_by('-sent_at')
        .values('participant_id', 'phone_normalized', 'sent_at', 'message_used', 'message_index')[:200]
    )
    for s in sent_list:
        s['sent_at'] = s['sent_at'].isoformat() if s.get('sent_at') else None

    return Response({
        'success': True,
        'id': str(config.id),
        'group_id': str(group.id),
        'enabled': config.enabled,
        'message_templates': config.message_templates,
        'exclude_numbers': config.exclude_numbers,
        'min_delay_seconds': config.min_delay_seconds,
        'max_delay_seconds': config.max_delay_seconds,
        'max_per_run': config.max_per_run,
        'skip_saved_contacts': config.skip_saved_contacts,
        'last_run_at': config.last_run_at.isoformat() if config.last_run_at else None,
        'sent_count': sent_count,
        'eligible_count': config.cached_eligible_count,
        'eligible_count_cached_at': config.cached_eligible_at.isoformat() if config.cached_eligible_at else None,
        'participants_total': config.cached_participants_total,
        'sent_list': sent_list,
    })


@api_view(['POST'])
@permission_classes([IsSuperUser])
def whatsapp_outreach_run_now(request):
    """
    Encola la tarea de Celery que ejecuta el outreach para todos los grupos con outreach activado.
    Útil cuando Beat no está disparando la tarea o para ejecutar un ciclo "ahora" desde el panel.
    Requiere que el Celery worker esté corriendo para que la tarea se ejecute.
    Returns { "queued": true, "task_id": "..." }.
    """
    from apps.whatsapp.tasks import run_group_outreach

    task = run_group_outreach.delay()
    return Response({'queued': True, 'task_id': str(task.id)})


@api_view(['POST'])
@permission_classes([IsSuperUser])
def whatsapp_group_outreach_send_one(request, group_id):
    """
    Send one outreach message now to a randomly chosen eligible participant.
    Returns { "sent": true, "participant_id": "...", "phone_normalized": "..." } or
    { "sent": false, "error": "..." }.
    """
    from apps.whatsapp.services.group_outreach_service import send_one_outreach_now

    try:
        group = WhatsAppChat.objects.get(id=group_id)
    except WhatsAppChat.DoesNotExist:
        return Response({'error': 'Group not found'}, status=status.HTTP_404_NOT_FOUND)

    if group.type != 'group':
        return Response({'error': 'Chat is not a group'}, status=status.HTTP_400_BAD_REQUEST)

    config = GroupOutreachConfig.objects.filter(group=group).first()
    if not config:
        return Response({'sent': False, 'error': 'No hay configuración de outreach'}, status=status.HTTP_400_BAD_REQUEST)

    result = send_one_outreach_now(config)
    if result.get('sent'):
        return Response(result)
    return Response(result, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsSuperUser])
def whatsapp_experiences(request):
    """List all experiences with their WhatsApp group bindings."""
    import logging
    from apps.experiences.models import Experience
    from apps.whatsapp.services.experience_operator_service import ExperienceOperatorService
    
    logger = logging.getLogger(__name__)
    
    try:
        experiences = Experience.objects.select_related(
            'organizer'
        ).prefetch_related(
            'whatsapp_group_bindings__whatsapp_group',
            'whatsapp_group_bindings__tour_operator',
            'operator_bindings__tour_operator'
        ).filter(
            deleted_at__isnull=True
        ).order_by('-created_at')
        
        result = []
        for experience in experiences:
            # Use service to get group info
            group_info = ExperienceOperatorService.get_experience_whatsapp_group(experience)
            
            current_group = None
            is_using_default = False
            has_custom_binding = False
            
            if group_info:
                current_group = {
                    'id': group_info['id'],
                    'chat_id': group_info['chat_id'],
                    'name': group_info['name'],
                    'is_override': group_info.get('is_override', False)
                }
                is_using_default = not group_info.get('is_override', False)
                has_custom_binding = group_info.get('is_override', False)
            
            result.append({
                'id': str(experience.id),
                'title': experience.title,
                'slug': experience.slug,
                'organizer': {
                    'id': str(experience.organizer.id),
                    'name': experience.organizer.name
                } if experience.organizer else None,
                'current_whatsapp_group': current_group,
                'is_using_default_group': is_using_default,
                'has_custom_binding': has_custom_binding
            })
        
        return Response({
            'experiences': result,
            'total': len(result)
        })
    except Exception as e:
        logger.exception(f"Error fetching experiences: {e}")
        return Response({'experiences': [], 'total': 0})


@api_view(['PATCH'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def whatsapp_experience_group(request, experience_id):
    """Link/unlink a WhatsApp group to an experience."""
    import logging
    from apps.experiences.models import Experience
    from apps.whatsapp.services.experience_operator_service import ExperienceOperatorService
    
    logger = logging.getLogger(__name__)
    
    try:
        experience = Experience.objects.get(id=experience_id)
        
        group_id = request.data.get('group_id')  # Puede ser None para desvincular
        
        if group_id:
            # Vincular a un grupo específico usando el servicio
            try:
                binding = ExperienceOperatorService.create_experience_group_binding(
                    experience=experience,
                    whatsapp_group_id=group_id,
                    is_override=True
                )
                
                if not binding:
                    return Response(
                        {'error': 'Could not create binding. Group may not exist.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                return Response({
                    'success': True,
                    'experience_id': str(experience.id),
                    'group': {
                        'id': str(binding.whatsapp_group.id),
                        'chat_id': binding.whatsapp_group.chat_id,
                        'name': binding.whatsapp_group.name
                    },
                    'is_override': True
                })
            except ValueError as e:
                return Response(
                    {'error': str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            # Desvincular (eliminar binding personalizado, volverá a usar default)
            removed = ExperienceOperatorService.remove_experience_group_binding(
                experience=experience,
                only_overrides=True
            )
            
            if removed:
                return Response({
                    'success': True,
                    'experience_id': str(experience.id),
                    'group': None,
                    'message': 'Custom binding removed, will use operator default group'
                })
            else:
                return Response({
                    'success': True,
                    'experience_id': str(experience.id),
                    'group': None,
                    'message': 'No custom binding found to remove'
                })
            
    except Experience.DoesNotExist:
        return Response(
            {'error': 'Experience not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.exception(f"Error updating experience group binding: {e}")
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ----- Accommodations: list + link group (hierarchy: room > hotel > rental_hub) -----

from apps.whatsapp.services.accommodation_operator_service import AccommodationOperatorService


@api_view(['GET'])
@permission_classes([IsSuperUser])
def whatsapp_accommodations(request):
    """List all accommodations with their resolved WhatsApp group (hierarchy-aware)."""
    import logging
    logger = logging.getLogger(__name__)
    try:
        accommodations = Accommodation.objects.select_related(
            'hotel', 'rental_hub', 'organizer'
        ).prefetch_related(
            'whatsapp_group_bindings__whatsapp_group',
            'whatsapp_group_bindings__tour_operator',
            'operator_bindings__tour_operator',
        ).filter(
            deleted_at__isnull=True
        ).order_by('-created_at')

        result = []
        for acc in accommodations:
            group_info = AccommodationOperatorService.get_accommodation_whatsapp_group(acc)
            current_group = None
            is_using_default = False
            has_custom_binding = False
            if group_info:
                current_group = {
                    'id': group_info['id'],
                    'chat_id': group_info['chat_id'],
                    'name': group_info['name'],
                    'is_override': group_info.get('is_override', False),
                    'source': group_info.get('source', ''),
                }
                is_using_default = not group_info.get('is_override', False)
                has_custom_binding = group_info.get('is_override', False)

            result.append({
                'id': str(acc.id),
                'title': acc.title,
                'slug': acc.slug,
                'organizer': {'id': str(acc.organizer.id), 'name': acc.organizer.name} if acc.organizer else None,
                'hotel': {'id': str(acc.hotel.id), 'slug': acc.hotel.slug, 'name': acc.hotel.name} if acc.hotel else None,
                'rental_hub': {'id': str(acc.rental_hub.id), 'slug': acc.rental_hub.slug, 'name': acc.rental_hub.name} if acc.rental_hub else None,
                'current_whatsapp_group': current_group,
                'is_using_default_group': is_using_default,
                'has_custom_binding': has_custom_binding,
            })

        return Response({'accommodations': result, 'total': len(result)})
    except Exception as e:
        logger.exception("Error fetching accommodations for WhatsApp: %s", e)
        return Response({'accommodations': [], 'total': 0})


@api_view(['PATCH'])
@permission_classes([IsSuperUser])
def whatsapp_accommodation_group(request, accommodation_id):
    """Link or unlink a WhatsApp group to an accommodation (room-level override)."""
    import logging
    logger = logging.getLogger(__name__)
    try:
        acc = Accommodation.objects.get(id=accommodation_id)
    except Accommodation.DoesNotExist:
        return Response({'error': 'Accommodation not found'}, status=status.HTTP_404_NOT_FOUND)

    group_id = request.data.get('group_id')

    if group_id:
        try:
            binding = AccommodationOperatorService.create_accommodation_group_binding(
                accommodation=acc,
                whatsapp_group_id=group_id,
                is_override=True,
            )
            if not binding:
                return Response(
                    {'error': 'Could not create binding. Group may not exist.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return Response({
                'success': True,
                'accommodation_id': str(acc.id),
                'group': {
                    'id': str(binding.whatsapp_group.id),
                    'chat_id': binding.whatsapp_group.chat_id,
                    'name': binding.whatsapp_group.name,
                },
                'is_override': True,
            })
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    else:
        removed = AccommodationOperatorService.remove_accommodation_group_binding(acc, only_overrides=True)
        return Response({
            'success': True,
            'accommodation_id': str(acc.id),
            'group': None,
            'is_override': False,
            'removed_binding': removed,
        })


@api_view(['GET'])
@permission_classes([IsSuperUser])
def whatsapp_hotels(request):
    """List hotels with their default WhatsApp group (for reservation coordination)."""
    try:
        hotels = Hotel.objects.select_related('default_whatsapp_group').filter(
            is_active=True
        ).order_by('name')
        result = [
            {
                'id': str(h.id),
                'slug': h.slug,
                'name': h.name,
                'current_whatsapp_group': {
                    'id': str(h.default_whatsapp_group.id),
                    'chat_id': h.default_whatsapp_group.chat_id,
                    'name': h.default_whatsapp_group.name,
                } if h.default_whatsapp_group else None,
            }
            for h in hotels
        ]
        return Response({'hotels': result, 'total': len(result)})
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error fetching hotels for WhatsApp")
        return Response({'hotels': [], 'total': 0})


@api_view(['PATCH'])
@permission_classes([IsSuperUser])
def whatsapp_hotel_group(request, hotel_id):
    """Set or clear the default WhatsApp group for a hotel."""
    try:
        hotel = Hotel.objects.get(id=hotel_id)
    except Hotel.DoesNotExist:
        return Response({'error': 'Hotel not found'}, status=status.HTTP_404_NOT_FOUND)

    group_id = request.data.get('group_id')
    if group_id:
        try:
            group = WhatsAppChat.objects.get(id=group_id, type='group')
        except WhatsAppChat.DoesNotExist:
            return Response({'error': 'Group not found'}, status=status.HTTP_404_NOT_FOUND)
        hotel.default_whatsapp_group = group
        hotel.save(update_fields=['default_whatsapp_group', 'updated_at'])
        return Response({
            'success': True,
            'hotel_id': str(hotel.id),
            'group': {'id': str(group.id), 'chat_id': group.chat_id, 'name': group.name},
        })
    else:
        hotel.default_whatsapp_group = None
        hotel.save(update_fields=['default_whatsapp_group', 'updated_at'])
        return Response({
            'success': True,
            'hotel_id': str(hotel.id),
            'group': None,
        })


@api_view(['GET'])
@permission_classes([IsSuperUser])
def whatsapp_rental_hubs(request):
    """List rental hubs (centrales) with their default WhatsApp group."""
    try:
        hubs = RentalHub.objects.select_related('default_whatsapp_group').filter(
            is_active=True
        ).order_by('name')
        result = [
            {
                'id': str(h.id),
                'slug': h.slug,
                'name': h.name,
                'current_whatsapp_group': {
                    'id': str(h.default_whatsapp_group.id),
                    'chat_id': h.default_whatsapp_group.chat_id,
                    'name': h.default_whatsapp_group.name,
                } if h.default_whatsapp_group else None,
            }
            for h in hubs
        ]
        return Response({'rental_hubs': result, 'total': len(result)})
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error fetching rental hubs for WhatsApp")
        return Response({'rental_hubs': [], 'total': 0})


@api_view(['PATCH'])
@permission_classes([IsSuperUser])
def whatsapp_rental_hub_group(request, rental_hub_id):
    """Set or clear the default WhatsApp group for a rental hub (central)."""
    try:
        hub = RentalHub.objects.get(id=rental_hub_id)
    except RentalHub.DoesNotExist:
        return Response({'error': 'Rental hub not found'}, status=status.HTTP_404_NOT_FOUND)

    group_id = request.data.get('group_id')
    if group_id:
        try:
            group = WhatsAppChat.objects.get(id=group_id, type='group')
        except WhatsAppChat.DoesNotExist:
            return Response({'error': 'Group not found'}, status=status.HTTP_404_NOT_FOUND)
        hub.default_whatsapp_group = group
        hub.save(update_fields=['default_whatsapp_group', 'updated_at'])
        return Response({
            'success': True,
            'rental_hub_id': str(hub.id),
            'group': {'id': str(group.id), 'chat_id': group.chat_id, 'name': group.name},
        })
    else:
        hub.default_whatsapp_group = None
        hub.save(update_fields=['default_whatsapp_group', 'updated_at'])
        return Response({
            'success': True,
            'rental_hub_id': str(hub.id),
            'group': None,
        })


# Message types and placeholders for reservation flow (used by GET reservation-messages)
WHATSAPP_RESERVATION_MESSAGE_TYPES = [
    ('reservation_request', 'Solicitud de reserva al operador'),
    ('customer_waiting', 'Esperando confirmación del operador (al cliente)'),
    ('customer_confirmation', 'Confirmación al cliente'),
    ('customer_rejection', 'Rechazo al cliente'),
    ('payment_link', 'Link de pago al cliente'),
    ('payment_confirmed', 'Pago confirmado al cliente'),
    ('customer_availability_confirmed', 'Disponibilidad confirmada al cliente'),
    ('customer_confirm_free', 'Confirmar reserva gratuita (al cliente)'),
    ('ticket_info', 'Información del ticket'),
    ('reminder', 'Recordatorio al operador'),
]
WHATSAPP_RESERVATION_PLACEHOLDERS = [
    {'key': 'contacto', 'description': 'Nombre del contacto del operador'},
    {'key': 'experiencia', 'description': 'Nombre de la experiencia/tour/alojamiento'},
    {'key': 'fecha', 'description': 'Fecha de la reserva (ej: 15 de marzo de 2026)'},
    {'key': 'hora', 'description': 'Hora de la reserva (ej: 10:00)'},
    {'key': 'pasajeros', 'description': 'Número total de pasajeros'},
    {'key': 'adultos', 'description': 'Número de adultos'},
    {'key': 'ninos', 'description': 'Número de niños'},
    {'key': 'infantes', 'description': 'Número de infantes'},
    {'key': 'precio', 'description': 'Precio total formateado (ej: $45.000)'},
    {'key': 'nombre_cliente', 'description': 'Nombre del cliente'},
    {'key': 'telefono_cliente', 'description': 'Teléfono del cliente'},
    {'key': 'codigo', 'description': 'Código de reserva'},
    {'key': 'link_pago', 'description': 'Link de pago (si aplica)'},
    {'key': 'link_pago_mensaje', 'description': 'Frase con link de pago para confirmación'},
    {'key': 'punto_encuentro', 'description': 'Punto de encuentro'},
    {'key': 'instrucciones', 'description': 'Instrucciones adicionales'},
    {'key': 'pasos_siguientes', 'description': 'Pasos siguientes (pago o confirmar)'},
    {'key': 'check_in', 'description': 'Fecha check-in (alojamientos)'},
    {'key': 'check_out', 'description': 'Fecha check-out (alojamientos)'},
    {'key': 'guests', 'description': 'Número de huéspedes (alojamientos)'},
    {'key': 'pickup_date', 'description': 'Fecha recogida (rent a car)'},
    {'key': 'return_date', 'description': 'Fecha devolución (rent a car)'},
    {'key': 'pickup_time', 'description': 'Hora recogida (rent a car)'},
    {'key': 'return_time', 'description': 'Hora devolución (rent a car)'},
]


@api_view(['GET', 'PATCH'])
@permission_classes([IsSuperUser])
def whatsapp_reservation_messages(request):
    """
    GET: Return global platform templates (stored + defaults) and placeholders.
    PATCH: Update global templates. Body: { "templates": { "message_type": "text", ... } }
    """
    if request.method == 'GET':
        config = WhatsAppReservationMessageConfig.objects.filter(
            config_key=WhatsAppReservationMessageConfig.CONFIG_KEY
        ).first()
        stored = (config.templates if config else None) or {}
        # Merge: for each type return stored if non-empty, else default
        templates = {}
        for key, _label in WHATSAPP_RESERVATION_MESSAGE_TYPES:
            custom = (stored.get(key) or '').strip()
            if custom:
                templates[key] = custom
            else:
                templates[key] = DEFAULT_TEMPLATES.get(key, '')
        return Response({
            'message_types': [{'key': k, 'label': v} for k, v in WHATSAPP_RESERVATION_MESSAGE_TYPES],
            'templates': templates,
            'placeholders': WHATSAPP_RESERVATION_PLACEHOLDERS,
        })

    # PATCH
    data = request.data or {}
    templates_input = data.get('templates')
    if not isinstance(templates_input, dict):
        return Response(
            {'detail': "Se requiere 'templates' (objeto message_type -> texto)."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    config, _ = WhatsAppReservationMessageConfig.objects.get_or_create(
        config_key=WhatsAppReservationMessageConfig.CONFIG_KEY,
        defaults={'templates': {}},
    )
    current = dict(config.templates or {})
    for key, _ in WHATSAPP_RESERVATION_MESSAGE_TYPES:
        if key in templates_input:
            val = templates_input[key]
            if isinstance(val, str):
                if val.strip():
                    current[key] = val.strip()
                else:
                    current.pop(key, None)
    config.templates = current
    config.save(update_fields=['templates', 'updated_at'])
    # Return same shape as GET
    stored = config.templates or {}
    templates = {}
    for key, _ in WHATSAPP_RESERVATION_MESSAGE_TYPES:
        custom = (stored.get(key) or '').strip()
        if custom:
            templates[key] = custom
        else:
            templates[key] = DEFAULT_TEMPLATES.get(key, '')
    return Response({
        'message_types': [{'key': k, 'label': v} for k, v in WHATSAPP_RESERVATION_MESSAGE_TYPES],
        'templates': templates,
        'placeholders': WHATSAPP_RESERVATION_PLACEHOLDERS,
    })


@api_view(['GET', 'PATCH'])
@permission_classes([IsSuperUser])
def whatsapp_experience_reservation_messages(request, experience_id):
    """
    GET: Return reservation message overrides for this experience (empty = use global).
    PATCH: Update overrides. Body: { "templates": { "message_type": "text", ... } }
    """
    try:
        experience = Experience.objects.get(id=experience_id)
    except Experience.DoesNotExist:
        return Response({'detail': 'Experiencia no encontrada.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        overrides = getattr(experience, 'whatsapp_message_templates', None) or {}
        if not isinstance(overrides, dict):
            overrides = {}
        # Return overrides only; frontend can merge with global for display
        return Response({
            'experience_id': str(experience.id),
            'templates': overrides,
            'message_types': [{'key': k, 'label': v} for k, v in WHATSAPP_RESERVATION_MESSAGE_TYPES],
            'placeholders': WHATSAPP_RESERVATION_PLACEHOLDERS,
        })

    # PATCH
    data = request.data or {}
    templates_input = data.get('templates')
    if not isinstance(templates_input, dict):
        return Response(
            {'detail': "Se requiere 'templates' (objeto message_type -> texto)."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    current = dict(experience.whatsapp_message_templates or {})
    for key, _ in WHATSAPP_RESERVATION_MESSAGE_TYPES:
        if key in templates_input:
            val = templates_input[key]
            if isinstance(val, str):
                if val.strip():
                    current[key] = val.strip()
                else:
                    current.pop(key, None)
    experience.whatsapp_message_templates = current
    experience.save(update_fields=['whatsapp_message_templates'])
    return Response({
        'experience_id': str(experience.id),
        'templates': experience.whatsapp_message_templates or {},
        'message_types': [{'key': k, 'label': v} for k, v in WHATSAPP_RESERVATION_MESSAGE_TYPES],
        'placeholders': WHATSAPP_RESERVATION_PLACEHOLDERS,
    })


def _reservation_messages_entity_view(request, entity, entity_id_field: str):
    """Shared GET/PATCH logic for reservation messages on an entity (Accommodation, Hotel, RentalHub)."""
    if request.method == 'GET':
        overrides = getattr(entity, 'whatsapp_message_templates', None) or {}
        if not isinstance(overrides, dict):
            overrides = {}
        return Response({
            entity_id_field: str(entity.id),
            'templates': overrides,
            'message_types': [{'key': k, 'label': v} for k, v in WHATSAPP_RESERVATION_MESSAGE_TYPES],
            'placeholders': WHATSAPP_RESERVATION_PLACEHOLDERS,
        })
    data = request.data or {}
    templates_input = data.get('templates')
    if not isinstance(templates_input, dict):
        return Response(
            {'detail': "Se requiere 'templates' (objeto message_type -> texto)."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    current = dict(getattr(entity, 'whatsapp_message_templates', None) or {})
    for key, _ in WHATSAPP_RESERVATION_MESSAGE_TYPES:
        if key in templates_input:
            val = templates_input[key]
            if isinstance(val, str):
                if val.strip():
                    current[key] = val.strip()
                else:
                    current.pop(key, None)
    entity.whatsapp_message_templates = current
    entity.save()
    return Response({
        entity_id_field: str(entity.id),
        'templates': entity.whatsapp_message_templates or {},
        'message_types': [{'key': k, 'label': v} for k, v in WHATSAPP_RESERVATION_MESSAGE_TYPES],
        'placeholders': WHATSAPP_RESERVATION_PLACEHOLDERS,
    })


@api_view(['GET', 'PATCH'])
@permission_classes([IsSuperUser])
def whatsapp_accommodation_reservation_messages(request, accommodation_id):
    """GET/PATCH reservation message overrides for an accommodation (room/unit)."""
    try:
        accommodation = Accommodation.objects.get(id=accommodation_id)
    except Accommodation.DoesNotExist:
        return Response({'detail': 'Alojamiento no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
    return _reservation_messages_entity_view(request, accommodation, 'accommodation_id')


@api_view(['GET', 'PATCH'])
@permission_classes([IsSuperUser])
def whatsapp_hotel_reservation_messages(request, hotel_id):
    """GET/PATCH reservation message overrides for a hotel."""
    try:
        hotel = Hotel.objects.get(id=hotel_id)
    except Hotel.DoesNotExist:
        return Response({'detail': 'Hotel no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
    return _reservation_messages_entity_view(request, hotel, 'hotel_id')


@api_view(['GET', 'PATCH'])
@permission_classes([IsSuperUser])
def whatsapp_rental_hub_reservation_messages(request, rental_hub_id):
    """GET/PATCH reservation message overrides for a rental hub (central)."""
    try:
        rental_hub = RentalHub.objects.get(id=rental_hub_id)
    except RentalHub.DoesNotExist:
        return Response({'detail': 'Central de arrendamiento no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
    return _reservation_messages_entity_view(request, rental_hub, 'rental_hub_id')


@api_view(['GET'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def whatsapp_operator_detail(request, operator_id):
    """Get detailed information about a tour operator."""
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        operator = TourOperator.objects.select_related(
            'organizer', 'default_whatsapp_group'
        ).prefetch_related(
            'experience_bindings__experience'
        ).get(id=operator_id)
        
        # Get experiences linked to this operator
        experiences = []
        for binding in operator.experience_bindings.filter(is_active=True):
            experiences.append({
                'id': str(binding.experience.id),
                'title': binding.experience.title,
                'slug': binding.experience.slug
            })
        
        result = {
            'id': str(operator.id),
            'name': operator.name,
            'contact_name': operator.contact_name,
            'contact_phone': operator.contact_phone,
            'contact_email': operator.contact_email,
            'whatsapp_number': operator.whatsapp_number or '',
            'is_active': operator.is_active,
            'is_system_created': operator.is_system_created if hasattr(operator, 'is_system_created') else False,
            'organizer': {
                'id': str(operator.organizer.id),
                'name': operator.organizer.name,
                'slug': operator.organizer.slug
            } if operator.organizer else None,
            'default_whatsapp_group': {
                'id': str(operator.default_whatsapp_group.id),
                'chat_id': operator.default_whatsapp_group.chat_id,
                'name': operator.default_whatsapp_group.name
            } if operator.default_whatsapp_group else None,
            'experiences': experiences,
            'experiences_count': len(experiences)
        }
        
        return Response(result)
    except TourOperator.DoesNotExist:
        return Response(
            {'error': 'Operator not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.exception(f"Error fetching operator details: {e}")
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PATCH'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def whatsapp_operator_default_group(request, operator_id):
    """Set default WhatsApp group for an operator."""
    import logging
    from apps.whatsapp.models import WhatsAppChat
    
    logger = logging.getLogger(__name__)
    
    try:
        operator = TourOperator.objects.get(id=operator_id)
        
        group_id = request.data.get('group_id')  # Puede ser None para desasignar
        
        if group_id:
            try:
                group = WhatsAppChat.objects.get(id=group_id, type='group')
                operator.default_whatsapp_group = group
                operator.save(update_fields=['default_whatsapp_group'])
                
                logger.info(f"✅ Set default group '{group.name}' for operator '{operator.name}'")
                
                return Response({
                    'success': True,
                    'operator_id': str(operator.id),
                    'default_group': {
                        'id': str(group.id),
                        'chat_id': group.chat_id,
                        'name': group.name
                    }
                })
            except WhatsAppChat.DoesNotExist:
                return Response(
                    {'error': 'Group not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            # Desasignar grupo predeterminado
            operator.default_whatsapp_group = None
            operator.save(update_fields=['default_whatsapp_group'])
            
            logger.info(f"✅ Removed default group for operator '{operator.name}'")
            
            return Response({
                'success': True,
                'operator_id': str(operator.id),
                'default_group': None,
                'message': 'Default group removed'
            })
            
    except TourOperator.DoesNotExist:
        return Response(
            {'error': 'Operator not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.exception(f"Error updating operator default group: {e}")
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

