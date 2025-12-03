"""
🚀 ENTERPRISE TICKET VALIDATION SYSTEM
Sistema de validación de tickets nivel enterprise que supera a Ticketmaster
"""

from django.shortcuts import render
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.utils import timezone
from django.db import transaction
from django.db.models import Q, Count, Sum
from apps.events.models import Event, Ticket
from apps.organizers.models import Organizer, OrganizerUser
from apps.validation.models import ValidatorSession, TicketValidationLog, TicketNote, EventValidationStats
from apps.validation.serializers import (
    ValidatorSessionSerializer, TicketValidationLogSerializer,
    TicketNoteSerializer, TicketDetailSerializer
)
from django.contrib.auth.models import User
import hashlib
import json
from datetime import datetime, timedelta
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes


@extend_schema(
    summary="🚀 ENTERPRISE: Iniciar Sesión de Validador",
    description="Inicia una sesión de validación para un evento específico con tracking completo",
    responses={200: {"description": "Sesión iniciada exitosamente"}}
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def start_validator_session(request):
    """
    🚀 ENTERPRISE: Iniciar sesión de validador
    
    Body:
    {
        "validator_name": "Juan Pérez",
        "event_id": 123,
        "device_info": {...},
        "location": {"lat": -33.4569, "lng": -70.6483}
    }
    """
    try:
        # Obtener organizador
        organizer_user = OrganizerUser.objects.get(user=request.user)
        organizer = organizer_user.organizer
        
        # Validar evento
        event_id = request.data.get('event_id')
        event = Event.objects.get(id=event_id, organizer=organizer)
        
        # Cerrar sesiones activas previas
        ValidatorSession.objects.filter(
            user=request.user,
            event=event,
            is_active=True
        ).update(is_active=False, end_time=timezone.now())
        
        # Crear nueva sesión
        session = ValidatorSession.objects.create(
            validator_name=request.data.get('validator_name', 'Validador'),
            organizer=organizer,
            event=event,
            user=request.user,
            device_info=request.data.get('device_info', {}),
            location=request.data.get('location', {})
        )
        
        return Response({
            'success': True,
            'session_id': session.id,
            'validator_name': session.validator_name,
            'event': {
                'id': event.id,
                'title': event.title,
                'start_date': event.start_date,
                'total_tickets': event.tickets.count(),
                'checked_in': event.tickets.filter(check_in_status='checked_in').count()
            },
            'message': f'Sesión iniciada para {session.validator_name}'
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error iniciando sesión: {str(e)}'
        }, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    summary="🚀 ENTERPRISE: Validar Ticket QR Ultra-Rápido",
    description="Validación enterprise de tickets con todas las verificaciones de seguridad y business logic"
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def validate_ticket_enterprise(request):
    """
    🚀 ENTERPRISE: Validación de ticket ultra-robusta
    
    Features:
    - Validación de seguridad completa
    - Verificación de fechas y horarios
    - Control de límites de ingreso
    - Tracking completo de sesión
    - Logs detallados
    - Sincronización offline/online
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        with transaction.atomic():
            # 1. Obtener datos de entrada
            ticket_number = request.data.get('ticket_number')
            session_id = request.data.get('session_id')
            qr_data = request.data.get('qr_data', '')
            scan_time_ms = request.data.get('scan_time_ms', 0)
            device_location = request.data.get('device_location', {})
            
            logger.info("=" * 60)
            logger.info("🎫 BACKEND VALIDATION REQUEST")
            logger.info("=" * 60)
            logger.info(f"  ├─ Ticket Number: {ticket_number}")
            logger.info(f"  ├─ Session ID: {session_id}")
            logger.info(f"  ├─ QR Data: {qr_data}")
            logger.info(f"  ├─ Scan Time: {scan_time_ms}ms")
            logger.info(f"  └─ User: {request.user}")
            
            if not ticket_number or not session_id:
                logger.warning("  └─ ❌ MISSING DATA")
                return Response({
                    'valid': False,
                    'error': 'MISSING_DATA',
                    'message': 'ticket_number y session_id son requeridos'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # 2. Validar sesión activa
            try:
                session = ValidatorSession.objects.get(
                    id=session_id,
                    user=request.user,
                    is_active=True
                )
                logger.info(f"  ├─ ✅ Session found: {session.event.title}")
            except ValidatorSession.DoesNotExist:
                logger.warning("  └─ ❌ INVALID SESSION")
                return Response({
                    'valid': False,
                    'error': 'INVALID_SESSION',
                    'message': 'Sesión de validador inválida o expirada'
                }, status=status.HTTP_401_UNAUTHORIZED)
            
            # 3. Buscar ticket
            logger.info(f"  ├─ Searching ticket in event: {session.event.id}")
            try:
                ticket = Ticket.objects.select_related(
                    'order_item__order__event',
                    'order_item__ticket_tier'
                ).get(
                    ticket_number=ticket_number,
                    order_item__order__event=session.event
                )
                logger.info(f"  ├─ ✅ Ticket found!")
                logger.info(f"  │  ├─ ID: {ticket.id}")
                logger.info(f"  │  ├─ Number: {ticket.ticket_number}")
                logger.info(f"  │  ├─ Name: {ticket.first_name} {ticket.last_name}")
                logger.info(f"  │  ├─ Status: {ticket.status}")
                logger.info(f"  │  └─ Check-in Status: {ticket.check_in_status}")
            except Ticket.DoesNotExist:
                logger.warning(f"  └─ ❌ TICKET NOT FOUND: {ticket_number}")
                # Log intento fallido
                TicketValidationLog.objects.create(
                    ticket=None,
                    validator_session=session,
                    action='validate',
                    status='error',
                    message=f'Ticket no encontrado: {ticket_number}',
                    scan_time_ms=scan_time_ms,
                    qr_data=qr_data,
                    device_location=device_location
                )
                
                session.total_scans += 1
                session.failed_validations += 1
                session.save()
                
                return Response({
                    'valid': False,
                    'error': 'TICKET_NOT_FOUND',
                    'message': 'Ticket no encontrado o no pertenece a este evento'
                })
            
            # 4. Validaciones de business logic
            logger.info("  ├─ Running business logic validations...")
            validation_errors = []
            
            # 4.1 Estado del ticket
            if ticket.status != 'active':
                error = f'Ticket no activo (estado: {ticket.get_status_display()})'
                validation_errors.append(error)
                logger.warning(f"  │  └─ ❌ {error}")
            
            # 4.2 Verificar si ya está checked-in
            if ticket.check_in_status == 'checked_in':
                error = f'Ticket ya ingresado el {ticket.check_in_time}'
                validation_errors.append(error)
                logger.warning(f"  │  └─ ❌ {error}")
            
            # 4.3 Verificar fechas del evento
            now = timezone.now()
            event = ticket.order_item.order.event
            
            # Verificar si el evento ya terminó
            if event.end_date and now > event.end_date:
                error = 'El evento ya terminó'
                validation_errors.append(error)
                logger.warning(f"  │  └─ ❌ {error}")
            
            # Verificar si es muy temprano (más de 2 horas antes)
            if event.start_date and now < (event.start_date - timedelta(hours=2)):
                error = 'Muy temprano para ingresar'
                validation_errors.append(error)
                logger.warning(f"  │  └─ ❌ {error}")
            
            # 4.4 Verificar límites de capacidad (si aplica)
            if hasattr(event, 'max_capacity') and event.max_capacity:
                current_checkins = Ticket.objects.filter(
                    order_item__order__event=event,
                    check_in_status='checked_in'
                ).count()
                
                if current_checkins >= event.max_capacity:
                    error = 'Evento lleno (capacidad máxima alcanzada)'
                    validation_errors.append(error)
                    logger.warning(f"  │  └─ ❌ {error}")
            
            # 5. Si hay errores, registrar y retornar
            if validation_errors:
                error_message = '; '.join(validation_errors)
                logger.warning(f"  └─ ❌ VALIDATION FAILED: {error_message}")
                
                TicketValidationLog.objects.create(
                    ticket=ticket,
                    validator_session=session,
                    action='validate',
                    status='error',
                    message=error_message,
                    scan_time_ms=scan_time_ms,
                    qr_data=qr_data,
                    device_location=device_location
                )
                
                session.total_scans += 1
                session.failed_validations += 1
                session.save()
                
                return Response({
                    'valid': False,
                    'error': 'VALIDATION_FAILED',
                    'message': error_message,
                    'ticket_info': {
                        'ticket_number': ticket.ticket_number,
                        'attendee_name': f'{ticket.first_name} {ticket.last_name}',
                        'status': ticket.status,
                        'check_in_status': ticket.check_in_status
                    }
                })
            
            # 6. ✅ VALIDACIÓN EXITOSA - Actualizar métricas
            logger.info("  ├─ ✅ All validations passed!")
            session.total_scans += 1
            session.successful_validations += 1
            session.save()
            logger.info(f"  ├─ Session stats: {session.successful_validations}/{session.total_scans}")
            
            # Log validación exitosa
            TicketValidationLog.objects.create(
                ticket=ticket,
                validator_session=session,
                action='validate',
                status='success',
                message='Ticket validado correctamente',
                scan_time_ms=scan_time_ms,
                qr_data=qr_data,
                device_location=device_location
            )
            
            # 7. Preparar respuesta completa
            response_data = {
                'valid': True,
                'message': 'Ticket válido - Listo para check-in',
                'ticket': {
                    'id': ticket.id,
                    'ticket_number': ticket.ticket_number,
                    'attendee_name': f'{ticket.first_name} {ticket.last_name}',
                    'email': ticket.email,
                    'status': ticket.status,
                    'check_in_status': ticket.check_in_status,
                    'tier_name': ticket.order_item.ticket_tier.name,
                    'tier_price': float(ticket.order_item.ticket_tier.price),
                    'form_data': ticket.form_data,
                    'order_info': {
                        'order_id': ticket.order_item.order.id,
                        'purchase_date': ticket.order_item.order.created_at,
                        'total_amount': float(ticket.order_item.order.total_amount)
                    }
                },
                'event': {
                    'id': event.id,
                    'title': event.title,
                    'start_date': event.start_date,
                    'location': event.location.name if event.location else None
                },
                'validation_info': {
                    'validator_name': session.validator_name,
                    'validation_time': timezone.now(),
                    'scan_time_ms': scan_time_ms
                }
            }
            
            logger.info("  └─ ✅ SUCCESS! Returning valid ticket")
            logger.info("=" * 60)
            return Response(response_data)
            
    except Exception as e:
        logger.error("=" * 60)
        logger.error(f"❌ SYSTEM ERROR: {str(e)}")
        logger.error("=" * 60)
        import traceback
        logger.error(traceback.format_exc())
        return Response({
            'valid': False,
            'error': 'SYSTEM_ERROR',
            'message': f'Error del sistema: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    summary="🚀 ENTERPRISE: Check-in de Ticket",
    description="Realizar check-in de ticket con tracking completo"
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def checkin_ticket_enterprise(request, ticket_id):
    """
    🚀 ENTERPRISE: Check-in de ticket con validaciones completas
    """
    try:
        with transaction.atomic():
            session_id = request.data.get('session_id')
            notes = request.data.get('notes', '')
            device_location = request.data.get('device_location', {})
            
            # Validar sesión
            session = ValidatorSession.objects.get(
                id=session_id,
                user=request.user,
                is_active=True
            )
            
            # Obtener ticket
            ticket = Ticket.objects.select_related(
                'order_item__order__event'
            ).get(
                id=ticket_id,
                order_item__order__event=session.event
            )
            
            # Verificar que se puede hacer check-in
            if ticket.check_in_status == 'checked_in':
                return Response({
                    'success': False,
                    'message': f'Ticket ya tiene check-in desde {ticket.check_in_time}'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Realizar check-in
            ticket.check_in_status = 'checked_in'
            ticket.checked_in = True  # Legacy field
            ticket.check_in_time = timezone.now()
            ticket.check_in_by = request.user
            ticket.status = 'used'
            ticket.save()
            
            # Actualizar métricas de sesión
            session.tickets_checked_in += 1
            session.save()
            
            # Log del check-in
            TicketValidationLog.objects.create(
                ticket=ticket,
                validator_session=session,
                action='check_in',
                status='success',
                message=f'Check-in realizado por {session.validator_name}',
                device_location=device_location,
                metadata={'notes': notes} if notes else {}
            )
            
            # Agregar nota si se proporcionó
            if notes:
                TicketNote.objects.create(
                    ticket=ticket,
                    user=request.user,
                    note=notes,
                    note_type='check_in'
                )
            
            return Response({
                'success': True,
                'message': 'Check-in realizado exitosamente',
                'ticket': {
                    'id': ticket.id,
                    'ticket_number': ticket.ticket_number,
                    'attendee_name': f'{ticket.first_name} {ticket.last_name}',
                    'check_in_status': ticket.check_in_status,
                    'check_in_time': ticket.check_in_time,
                    'checked_in_by': session.validator_name
                }
            })
            
    except Exception as e:
            return Response({
                'success': False,
                'message': f'Error en check-in: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    summary="🚀 ENTERPRISE: Finalizar Sesión de Validador",
    description="Finaliza una sesión de validación y genera reporte final"
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def end_validator_session(request, session_id):
    """
    🚀 ENTERPRISE: Finalizar sesión de validador
    """
    try:
        session = ValidatorSession.objects.get(
            id=session_id,
            user=request.user,
            is_active=True
        )
        
        session.is_active = False
        session.end_time = timezone.now()
        session.save()
        
        # Generar reporte final
        return Response({
            'success': True,
            'message': 'Sesión finalizada exitosamente',
            'session_report': ValidatorSessionSerializer(session).data
        })
        
    except ValidatorSession.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Sesión no encontrada o ya finalizada'
        }, status=status.HTTP_404_NOT_FOUND)


@extend_schema(
    summary="🚀 ENTERPRISE: Obtener Tickets de Evento",
    description="Lista todos los tickets de un evento con filtros avanzados"
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_event_tickets(request, event_id):
    """
    🚀 ENTERPRISE: Obtener tickets de evento con filtros
    """
    try:
        # Validar acceso al evento
        organizer_user = OrganizerUser.objects.get(user=request.user)
        event = Event.objects.get(id=event_id, organizer=organizer_user.organizer)
        
        # Filtros
        status_filter = request.GET.get('status')
        checkin_status = request.GET.get('checkin_status')
        search = request.GET.get('search')
        
        # Query base
        tickets = Ticket.objects.filter(
            order_item__order__event=event
        ).select_related(
            'order_item__order',
            'order_item__ticket_tier'
        ).prefetch_related('notes')
        
        # Aplicar filtros
        if status_filter:
            tickets = tickets.filter(status=status_filter)
        
        if checkin_status:
            tickets = tickets.filter(check_in_status=checkin_status)
        
        if search:
            tickets = tickets.filter(
                Q(ticket_number__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(email__icontains=search)
            )
        
        # Paginación
        from django.core.paginator import Paginator
        paginator = Paginator(tickets, 50)  # 50 tickets por página
        page = request.GET.get('page', 1)
        tickets_page = paginator.get_page(page)
        
        return Response({
            'success': True,
            'tickets': TicketDetailSerializer(tickets_page, many=True).data,
            'pagination': {
                'current_page': tickets_page.number,
                'total_pages': paginator.num_pages,
                'total_tickets': paginator.count,
                'has_next': tickets_page.has_next(),
                'has_previous': tickets_page.has_previous()
            }
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error obteniendo tickets: {str(e)}'
        }, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    summary="🚀 ENTERPRISE: Agregar Nota a Ticket",
    description="Agregar nota de validador a un ticket específico"
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_ticket_note(request, ticket_id):
    """
    🚀 ENTERPRISE: Agregar nota a ticket
    """
    try:
        ticket = Ticket.objects.get(id=ticket_id)
        session_id = request.data.get('session_id')
        
        # Validar sesión si se proporciona
        validator_session = None
        if session_id:
            validator_session = ValidatorSession.objects.get(
                id=session_id,
                user=request.user,
                is_active=True
            )
        
        # Crear nota
        note = TicketNote.objects.create(
            ticket=ticket,
            user=request.user,
            validator_session=validator_session,
            note_type=request.data.get('note_type', 'general'),
            title=request.data.get('title', ''),
            content=request.data.get('content', ''),
            is_important=request.data.get('is_important', False),
            metadata=request.data.get('metadata', {})
        )
        
        # Log de la acción
        if validator_session:
            TicketValidationLog.objects.create(
                ticket=ticket,
                validator_session=validator_session,
                action='note_added',
                status='success',
                message=f'Nota agregada: {note.title or note.content[:50]}',
                metadata={'note_id': note.id}
            )
        
        return Response({
            'success': True,
            'message': 'Nota agregada exitosamente',
            'note': TicketNoteSerializer(note).data
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error agregando nota: {str(e)}'
        }, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    summary="🚀 ENTERPRISE: Estadísticas de Validación de Evento",
    description="Obtener estadísticas en tiempo real de validación de evento"
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_event_validation_stats(request, event_id):
    """
    🚀 ENTERPRISE: Estadísticas de validación en tiempo real
    """
    try:
        # Validar acceso al evento
        organizer_user = OrganizerUser.objects.get(user=request.user)
        event = Event.objects.get(id=event_id, organizer=organizer_user.organizer)
        
        # Obtener o crear estadísticas
        stats, created = EventValidationStats.objects.get_or_create(
            event=event,
            defaults={
                'total_tickets': event.tickets.count(),
                'tickets_scanned': 0,
                'tickets_validated': 0,
                'tickets_checked_in': 0,
                'tickets_rejected': 0
            }
        )
        
        # Actualizar estadísticas en tiempo real
        stats.total_tickets = event.tickets.count()
        stats.tickets_checked_in = event.tickets.filter(check_in_status='checked_in').count()
        stats.active_validators = ValidatorSession.objects.filter(
            event=event,
            is_active=True
        ).count()
        
        # Estadísticas de sesiones activas
        active_sessions = ValidatorSession.objects.filter(
            event=event,
            is_active=True
        )
        
        sessions_data = []
        for session in active_sessions:
            sessions_data.append({
                'validator_name': session.validator_name,
                'start_time': session.start_time,
                'total_scans': session.total_scans,
                'successful_validations': session.successful_validations,
                'tickets_checked_in': session.tickets_checked_in,
                'success_rate': session.success_rate
            })
        
        stats.save()
        
        return Response({
            'success': True,
            'stats': EventValidationStatsSerializer(stats).data,
            'active_sessions': sessions_data,
            'real_time_metrics': {
                'pending_checkins': event.tickets.filter(check_in_status='pending').count(),
                'recent_checkins': event.tickets.filter(
                    check_in_status='checked_in',
                    check_in_time__gte=timezone.now() - timedelta(minutes=5)
                ).count(),
                'validation_rate_last_hour': TicketValidationLog.objects.filter(
                    validator_session__event=event,
                    created_at__gte=timezone.now() - timedelta(hours=1),
                    action='validate',
                    status='success'
                ).count()
            }
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error obteniendo estadísticas: {str(e)}'
        }, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    summary="🚀 ENTERPRISE: Estadísticas de Sesión",
    description="Obtener estadísticas detalladas de una sesión de validador"
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_session_stats(request, session_id):
    """
    🚀 ENTERPRISE: Estadísticas detalladas de sesión
    """
    try:
        session = ValidatorSession.objects.get(
            id=session_id,
            user=request.user
        )
        
        # Logs recientes de la sesión
        recent_logs = TicketValidationLog.objects.filter(
            validator_session=session
        ).order_by('-created_at')[:20]
        
        return Response({
            'success': True,
            'session': ValidatorSessionSerializer(session).data,
            'recent_activity': TicketValidationLogSerializer(recent_logs, many=True).data,
            'performance_metrics': {
                'average_scan_time': session.average_scan_time_ms,
                'throughput_per_hour': session.throughput_per_hour,
                'success_rate': session.success_rate,
                'error_rate': (session.failed_validations / max(session.total_scans, 1)) * 100
            }
        })
        
    except ValidatorSession.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Sesión no encontrada'
        }, status=status.HTTP_404_NOT_FOUND)
