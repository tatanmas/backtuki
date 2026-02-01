"""SuperAdmin WhatsApp views."""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from .permissions import IsSuperUser  # ENTERPRISE: Solo superusers autenticados
from rest_framework import status
from django.utils import timezone

from apps.whatsapp.models import (
    WhatsAppSession, WhatsAppReservationRequest, TourOperator, 
    ExperienceOperatorBinding, WhatsAppMessage, WhatsAppChat
)
from apps.whatsapp.services.whatsapp_client import WhatsAppWebService
from apps.experiences.models import Experience


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
            return Response({'qr': None}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'qr': None, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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
    is_reservation_related = request.query_params.get('is_reservation_related')
    has_code = request.query_params.get('has_code')
    date_from = request.query_params.get('date_from')
    date_to = request.query_params.get('date_to')
    
    try:
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
        # Ordenar por timestamp ascendente (cronológico: más antiguos primero)
        # Los mensajes sin timestamp se mostrarán al final
        for msg in queryset.order_by('timestamp')[:100]:
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
                # Log detallado para debugging
                logger.info(f"📨 API Response - Message {msg.id}: timestamp={timestamp_value}, type={msg.type}, year={msg.timestamp.year if msg.timestamp else 'N/A'}")
            elif hasattr(msg, 'created_at') and msg.created_at:
                # Fallback a created_at si timestamp no está disponible
                timestamp_value = msg.created_at.isoformat()
                logger.warning(f"⚠️ Message {msg.id} using created_at as timestamp: {timestamp_value}")
            else:
                # Último fallback: usar timezone.now() (ya importado al inicio)
                timestamp_value = timezone.now().isoformat()
                logger.warning(f"⚠️ Message {msg.id} using now() as timestamp: {timestamp_value}")
            
            messages.append({
                'id': str(msg.id),
                'whatsapp_id': msg.whatsapp_id,
                'phone': msg.phone,
                'type': msg.type,
                'content': msg.content[:200] if msg.content else '',  # Truncate for list view
                'full_content': msg.content or '',
                'timestamp': timestamp_value,
                'processed': msg.processed,
                'chat': chat_data,
                'reservation_code': msg.reservation_code,
                'is_reservation_related': msg.is_reservation_related,
                'linked_reservation_request_id': linked_reservation_request_id,
                'is_automated': is_automated,
                'metadata': message_metadata  # Incluir metadata con sender_name para grupos
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
        
        # Sincronizar chats desde Node.js para mantener información actualizada
        try:
            from apps.whatsapp.services.sync_service import WhatsAppSyncService
            
            sync_service = WhatsAppSyncService()
            sync_result = sync_service.sync_all_chats()
            logger.info(f"Chats sync: {sync_result['created']} created, {sync_result['updated']} updated")
        except Exception as sync_error:
            logger.error(f"Error syncing chats from Node.js service: {sync_error}", exc_info=True)
            # Continuar con chats existentes
        
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
            # Para grupos, usar el chat_id completo (ya incluye @g.us)
            result = whatsapp_service.send_message(phone, text, group_id=chat_id)
        else:
            # Para chats individuales, usar el número de teléfono
            # Asegurarse de que el chat_id no tenga @c.us si es individual
            clean_phone = phone.replace('@c.us', '').replace('@g.us', '')
            result = whatsapp_service.send_message(clean_phone, text)
        
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
            ordered_groups = groups.order_by('-last_message_at', '-created_at')
        except Exception:
            ordered_groups = groups.order_by('-created_at')
        
        for group in ordered_groups:
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
            
            result.append({
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


@api_view(['GET'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
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

