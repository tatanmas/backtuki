"""Views for events API."""

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, permissions, filters, status, mixins
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from drf_spectacular.utils import extend_schema, OpenApiParameter
from django.utils import timezone
from django.db.models import F, Sum, Count, Q
from django.utils.text import slugify
from django.shortcuts import get_object_or_404
from django.conf import settings
import uuid
import os
from django.db import transaction
from django.db.models import Count, Sum, F, Q, Value
from django.db.models.functions import Coalesce
from django.http import Http404, JsonResponse
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from datetime import timedelta

from core.permissions import IsOrganizer, HasEventModule
from apps.events.models import (
    Event,
    EventCategory,
    Location,
    TicketTier,
    TicketCategory,
    Order,
    OrderItem,
    Ticket,
    TicketHold,
    Coupon,
    EventCommunication,
    EventImage,
)
from apps.forms.models import Form, FormField
from apps.forms.serializers import FormFieldSerializer
from apps.organizers.models import OrganizerUser
from .serializers import (
    EventListSerializer,
    EventDetailSerializer,
    EventCreateSerializer,
    EventUpdateSerializer,
    EventAvailabilitySerializer,
    BookingSerializer,
    EventCategorySerializer,
    LocationSerializer,
    TicketTierSerializer,
    TicketTierCreateUpdateSerializer,
    TicketCategorySerializer,
    OrderSerializer,
    OrderDetailSerializer,
    TicketSerializer,
    CouponSerializer,
    EventCommunicationSerializer,
)


class EventViewSet(viewsets.ModelViewSet):
    """ViewSet for Event model."""
    
    queryset = Event.objects.all()
    serializer_class = EventListSerializer
    permission_classes = [IsAuthenticated]
    
    def get_organizer(self):
        """Obtener el organizador asociado al usuario actual."""
        try:
            # Handle anonymous users
            if not self.request.user.is_authenticated:
                return None
            organizer_user = OrganizerUser.objects.get(user=self.request.user)
            return organizer_user.organizer
        except OrganizerUser.DoesNotExist:
            return None
    
    def get_queryset(self):
        """Return events based on user permissions."""
        # For public endpoints like book/reserve, allow access to all published events
        if self.action in ['book', 'reserve', 'availability']:
            return Event.objects.filter(status='published')
            
        organizer = self.get_organizer()
        print(f"DEBUG - EventViewSet.get_queryset - User: {self.request.user.id if self.request.user.is_authenticated else 'Anonymous'}")
        print(f"DEBUG - EventViewSet.get_queryset - Organizer: {organizer.id if organizer else 'None'}")
        
        if not organizer:
            print("DEBUG - EventViewSet.get_queryset - No organizer found, returning empty queryset")
            return Event.objects.none()
        
        queryset = self.queryset.filter(organizer=organizer)
        print(f"DEBUG - EventViewSet.get_queryset - Found {queryset.count()} events for organizer")
        
        return queryset
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'list':
            return EventListSerializer
        if self.action == 'retrieve':
            return EventDetailSerializer
        if self.action == 'create':
            return EventCreateSerializer
        if self.action in ['update', 'partial_update']:
            return EventUpdateSerializer
        if self.action == 'availability':
            return EventAvailabilitySerializer
        if self.action == 'book':
            return BookingSerializer
        return EventDetailSerializer
    def get_permissions(self):
        """Allow public access to availability and booking endpoints."""
        if self.action in ['availability', 'book', 'reserve']:
            return [permissions.AllowAny()]
        return super().get_permissions()
    
    def get_serializer_context(self):
        """Add additional context to serializer."""
        context = super().get_serializer_context()
        if self.action == 'book':
            context['event_id'] = self.kwargs.get('pk')
        return context
    
    def retrieve(self, request, *args, **kwargs):
        """Retrieve a single event with debugging."""
        event_id = kwargs.get('pk')
        print(f"DEBUG - EventViewSet.retrieve - Attempting to retrieve event ID: {event_id}")
        
        try:
            instance = self.get_object()
            print(f"DEBUG - EventViewSet.retrieve - Found event: {instance.title} (ID: {instance.id}, Status: {instance.status})")
            serializer = self.get_serializer(instance)
            return Response(serializer.data)
        except Exception as e:
            print(f"DEBUG - EventViewSet.retrieve - Error retrieving event {event_id}: {str(e)}")
            raise

    def list(self, request, *args, **kwargs):
        """List events with optional filters."""
        queryset = self.get_queryset()
        
        # Apply filters
        event_type = request.query_params.getlist('type', [])
        if event_type:
            queryset = queryset.filter(type__in=event_type)
        
        start_date = request.query_params.get('start_date')
        if start_date:
            queryset = queryset.filter(start_date__gte=start_date)
        
        end_date = request.query_params.get('end_date')
        if end_date:
            queryset = queryset.filter(start_date__lte=end_date)
        
        location = request.query_params.get('location')
        if location:
            location_terms = location.lower()
            queryset = queryset.filter(
                Q(location__city__icontains=location_terms) |
                Q(location__country__icontains=location_terms) |
                Q(location__name__icontains=location_terms)
            )
        
        categories = request.query_params.getlist('category', [])
        if categories:
            queryset = queryset.filter(category__name__in=categories)
        
        # Pagination
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def availability(self, request, pk=None):
        """Get ticket availability for an event."""
        event = self.get_object()
        serializer = self.get_serializer(event)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def book(self, request, pk=None):
        """🚀 ENTERPRISE: Book tickets for an event."""
        import logging
        logger = logging.getLogger(__name__)
        
        event = self.get_object()
        logger.info(f'📦 BOOKING: Attempting to book tickets for event {event.title} ({event.id})')
        logger.info(f'📦 BOOKING: Request data: {request.data}')
        
        # Ensure event is published
        if event.status != 'published':
            logger.warning(f'📦 BOOKING: Event {event.id} not published (status: {event.status})')
            return Response({"detail": "Event not available for booking."}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Create a clean context without request.user to avoid AnonymousUser issues
            context = {'event_id': pk}
            if request.user.is_authenticated:
                context['request'] = request
            
            serializer = self.get_serializer(data=request.data, context=context)
            if not serializer.is_valid():
                logger.error(f'📦 BOOKING: Validation errors: {serializer.errors}')
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
            booking = serializer.save()
            logger.info(f'📦 BOOKING: Successfully created booking: {booking}')
            return Response(booking, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f'📦 BOOKING: Unexpected error: {str(e)}')
            import traceback
            logger.error(f'📦 BOOKING: Traceback: {traceback.format_exc()}')
            return Response({"detail": f"Booking failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def reserve(self, request, pk=None):
        """🚀 ENTERPRISE: Reserve tickets with expiration to prevent overselling."""
        event = self.get_object()
        if event.status != 'published':
            return Response({"detail": "Event not available for reservations."}, status=status.HTTP_400_BAD_REQUEST)

        tickets = request.data.get('tickets', [])
        reservation_id = request.data.get('reservationId')
        hold_minutes = int(request.data.get('holdMinutes', 15))

        if not isinstance(tickets, list) or not tickets:
            return Response({"detail": "Tickets payload is required."}, status=status.HTTP_400_BAD_REQUEST)

        now = timezone.now()
        expires_at = now + timedelta(minutes=hold_minutes)

        with transaction.atomic():
            # 🚀 ENTERPRISE: Clean expired holds for these tiers before proceeding
            tier_ids = [t.get('tierId') for t in tickets if t.get('tierId')]
            expired_holds = TicketHold.objects.select_for_update().filter(
                ticket_tier_id__in=tier_ids,
                released=False,
                expires_at__lte=now,
            )
            for hold in expired_holds:
                hold.release()

            # Get or create reservation order
            if reservation_id:
                try:
                    order = Order.objects.select_for_update().get(id=reservation_id, event=event)
                except Order.DoesNotExist:
                    return Response({"detail": "Reservation not found."}, status=status.HTTP_404_NOT_FOUND)
            else:
                order = Order.objects.create(
                    event=event,
                    email='tatan@tuki.cl',  # placeholder until email collection
                    first_name='Guest',
                    last_name='Tuki',
                    phone='',
                    subtotal=0,
                    service_fee=0,
                    total=0,
                    currency=event.ticket_tiers.first().currency if event.ticket_tiers.exists() else 'CLP',
                    status='pending'
                )

            # 🚀 ENTERPRISE: Index existing active holds for this order
            active_holds = list(TicketHold.objects.select_for_update().filter(
                order=order, released=False, expires_at__gt=now
            ))
            holds_by_tier = {}
            for hold in active_holds:
                holds_by_tier.setdefault(str(hold.ticket_tier_id), []).append(hold)

            # 🚀 ENTERPRISE: For each requested tier, adjust holds to match desired quantity
            result_items = []
            for t in tickets:
                tier_id = t.get('tierId')
                qty = int(t.get('quantity', 0))
                if not tier_id or qty < 0:
                    continue

                try:
                    tier = TicketTier.objects.select_for_update().get(id=tier_id, event=event)
                except TicketTier.DoesNotExist:
                    return Response({"detail": f"Ticket tier {tier_id} not found."}, status=status.HTTP_400_BAD_REQUEST)

                existing_qty = sum(h.quantity for h in holds_by_tier.get(str(tier_id), []) if not h.is_expired)

                if qty > existing_qty:
                    need = qty - existing_qty
                    if tier.available < need:
                        return Response({"detail": f"Not enough availability for {tier.name}."}, status=status.HTTP_400_BAD_REQUEST)
                    # 🚀 ENTERPRISE: Create one hold per unit to simplify partial release
                    for _ in range(need):
                        TicketHold.objects.create(
                            event=event,
                            ticket_tier=tier,
                            order=order,
                            quantity=1,
                            expires_at=expires_at,
                        )
                    # 🚀 ENTERPRISE: Decrease availability now (atomic stock control)
                    tier.available = F('available') - need
                    tier.save(update_fields=['available'])
                elif qty < existing_qty:
                    to_release = existing_qty - qty
                    # 🚀 ENTERPRISE: Release oldest holds first
                    holds_list = sorted(holds_by_tier.get(str(tier_id), []), key=lambda h: h.expires_at)
                    for hold in holds_list:
                        if to_release <= 0:
                            break
                        hold.release()
                        to_release -= hold.quantity

                result_items.append({
                    'tierId': str(tier_id),
                    'quantity': qty
                })

            return Response({
                'reservationId': str(order.id),
                'expiresAt': expires_at.isoformat(),
                'items': result_items,
                'holdMinutes': hold_minutes
            })
    
    @action(detail=False, methods=['get'])
    def categories(self, request):
        """Get list of event categories."""
        categories = EventCategory.objects.all()
        return Response([category.name for category in categories])
    
    @action(detail=False, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def upload(self, request):
        """🚀 ENTERPRISE IMAGE UPLOAD - Upload an image file and optionally associate with an event."""
        if 'file' not in request.FILES:
            return Response({'detail': 'No file found'}, status=status.HTTP_400_BAD_REQUEST)
        
        file_obj = request.FILES['file']
        event_id = request.data.get('event_id')  # Optional event association
        
        # Generate a unique filename
        filename = f"{uuid.uuid4().hex}.{file_obj.name.split('.')[-1]}"
        
        # Save file to media directory (enterprise implementation would use cloud storage)
        file_path = os.path.join(settings.MEDIA_ROOT, 'event_images', filename)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        try:
            with open(file_path, 'wb+') as destination:
                for chunk in file_obj.chunks():
                    destination.write(chunk)
            
            # Return the URL for the uploaded file (relative path)
            file_url = f"{settings.MEDIA_URL}event_images/{filename}"
            
            # If event_id is provided, create EventImage record
            if event_id:
                try:
                    event = Event.objects.get(id=event_id)
                    
                    # Verify user has permission to modify this event
                    organizer = self.get_organizer()
                    if not organizer or event.organizer != organizer:
                        # Clean up uploaded file if permission denied
                        if os.path.exists(file_path):
                            os.remove(file_path)
                        return Response({'detail': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
                    
                    # Create EventImage record
                    event_image = EventImage.objects.create(
                        event=event,
                        image=f"event_images/{filename}",  # Store relative path
                        alt=request.data.get('alt', file_obj.name),
                        type=request.data.get('type', 'image'),
                        order=event.images.count()  # Set order as current count
                    )
                    
                    print(f"[UPLOAD] ✅ Created EventImage record: {event_image.id} for event {event.id}")
                    
                    return Response({
                        'url': file_url,
                        'event_image_id': event_image.id,
                        'message': 'Image uploaded and associated with event successfully'
                    }, status=status.HTTP_201_CREATED)
                
                except Event.DoesNotExist:
                    # Clean up uploaded file if event doesn't exist
                    if os.path.exists(file_path):
                        os.remove(file_path)
                    return Response({'detail': 'Event not found'}, status=status.HTTP_404_NOT_FOUND)
            
            # If no event_id provided, just return the uploaded file URL
            print(f"[UPLOAD] ✅ File uploaded successfully: {file_url}")
            return Response({
                'url': file_url,
                'message': 'Image uploaded successfully'
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            # Clean up file if something went wrong
            if os.path.exists(file_path):
                os.remove(file_path)
            print(f"[UPLOAD] ❌ Error during upload: {str(e)}")
            return Response({'detail': f'Error uploading file: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['delete'], url_path=r'images/(?P<image_id>[^/.]+)')
    def delete_image(self, request, pk=None, image_id=None):
        """Delete an event image."""
        event = self.get_object()
        image = get_object_or_404(EventImage, id=image_id, event=event)
        
        # Delete file from storage (real implementation would handle cloud storage)
        if os.path.exists(image.image.path):
            os.remove(image.image.path)
        
        image.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def perform_create(self, serializer):
        # Obtener el organizador del usuario de manera correcta
        try:
            # Intentar obtener OrganizerUser para el usuario actual
            organizer_user = OrganizerUser.objects.get(user=self.request.user)
            organizer = organizer_user.organizer
            
            # Guardar el evento con el organizador encontrado
            event = serializer.save(
                organizer=organizer,
                status='draft'
            )
            
            # Ensure the event has an ID before returning
            event.refresh_from_db()
            return event
        except OrganizerUser.DoesNotExist:
            print(f"Error: Usuario {self.request.user.id} no tiene un organizer asociado")
            raise Exception("El usuario no tiene un organizador asociado")
    
    @action(detail=True, methods=['post'])
    def complete_draft(self, request, pk=None):
        """
        Marcar un evento borrador como completo y listo para añadir tickets y categorías.
        Verifica que el evento tenga toda la información básica necesaria.
        """
        event = self.get_object()
        
        # Log entire event details for debugging
        print(f"DEBUG - Complete Draft Request for event {pk}:")
        print(f"- title: '{event.title}'")
        print(f"- description length: {len(event.description) if event.description else 0}")
        print(f"- short_description: '{event.short_description}'")
        print(f"- start_date: {event.start_date}")
        print(f"- end_date: {event.end_date}")
        print(f"- location: {event.location.id if event.location else None}")
        print(f"- current status: {event.status}")
        
        # Modified: Allow any status to be marked as complete, but log a warning if not draft
        if event.status != 'draft':
            print(f"WARNING: Attempting to mark a non-draft event as complete (status: {event.status})")
            # We'll continue anyway to allow the user to fix issues
        
        # Verificar que el evento tenga toda la información básica necesaria
        required_fields = ['title', 'description', 'short_description', 'start_date', 'end_date', 'location']
        missing_fields = []
        
        for field in required_fields:
            value = getattr(event, field, None)
            if field == 'location':
                if value is None:
                    missing_fields.append(field)
            elif value is None or (isinstance(value, str) and value.strip() == ''):
                missing_fields.append(field)
        
        # Log the event data for debugging
        print(f"Event data for complete_draft: {event.title}, {event.short_description}, {event.start_date}, {event.end_date}")
        
        if missing_fields:
            return Response(
                {
                    'error': 'El evento no está completo',
                    'missing_fields': missing_fields
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Actualizar el estado del evento - setting to draft_complete regardless of previous status
        event.status = 'draft_complete'
        event.save()
        
        return Response({
            'status': 'draft_complete',
            'message': 'El evento ha sido marcado como completo y está listo para añadir tickets y categorías'
        })
    
    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        event = self.get_object()
        
        # Verificar que el evento esté en estado borrador completo
        if event.status != 'draft_complete':
            return Response(
                {'error': 'Solo los eventos con borrador completo pueden ser publicados'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validar que el evento tenga al menos una categoría y un ticket tier
        if not event.ticket_categories.exists():
            return Response(
                {'error': 'El evento debe tener al menos una categoría de tickets'},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        if not event.ticket_tiers.exists():
            return Response(
                {'error': 'El evento debe tener al menos un tipo de ticket'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Todo está bien, publicar el evento
        event.status = 'published'
        event.save()
        
        return Response({
            'status': 'published',
            'message': 'Evento publicado exitosamente'
        })

    def update(self, request, *args, **kwargs):
        """Override update to properly handle camelCase field names."""
        data = request.data.copy()
        
        # Map camelCase keys to snake_case for Django models
        if 'shortDescription' in data:
            print(f"ViewSet - Mapping shortDescription -> short_description: '{data['shortDescription']}'")
            data['short_description'] = data.pop('shortDescription')
        
        if 'startDate' in data:
            print(f"ViewSet - Mapping startDate -> start_date: '{data['startDate']}'")
            data['start_date'] = data.pop('startDate')
        
        if 'endDate' in data:
            print(f"ViewSet - Mapping endDate -> end_date: '{data['endDate']}'")
            data['end_date'] = data.pop('endDate')
        
        # Log all data being sent to serializer
        print(f"ViewSet - Data being sent to serializer: {data}")
        
        # Get instance for updating
        instance = self.get_object()
        
        # Create serializer with the mapped data
        serializer = self.get_serializer(instance, data=data, partial=kwargs.get('partial', False))
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        
        # Log the instance after update
        instance.refresh_from_db()
        print(f"ViewSet - After update: title={instance.title}, short_description={instance.short_description}")
        
        return Response(serializer.data)


class EventCategoryViewSet(viewsets.ModelViewSet):
    """
    API endpoint for event categories.
    """
    queryset = EventCategory.objects.all()
    serializer_class = EventCategorySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name']
    ordering = ['name']


class LocationViewSet(viewsets.ModelViewSet):
    """
    API endpoint for locations.
    """
    serializer_class = LocationSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['city', 'country']
    search_fields = ['name', 'address', 'city', 'country']
    ordering_fields = ['name', 'city', 'country']
    ordering = ['name']
    
    def get_organizer(self):
        """Obtener el organizador asociado al usuario actual."""
        try:
            organizer_user = OrganizerUser.objects.get(user=self.request.user)
            return organizer_user.organizer
        except OrganizerUser.DoesNotExist:
            return None
    
    def get_queryset(self):
        """
        Get locations for the current organizer if authenticated.
        """
        if not self.request.user.is_authenticated:
            return Location.objects.filter(events__status='active', events__visibility='public').distinct()
        
        organizer = self.get_organizer()
        if not organizer:
            return Location.objects.none()
        
        return Location.objects.filter(organizer=organizer)
    
    def get_permissions(self):
        """
        Get permissions based on action.
        """
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated(), IsOrganizer()]


class TicketCategoryViewSet(viewsets.ModelViewSet):
    """
    API endpoint for ticket categories.
    """
    serializer_class = TicketCategorySerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['event', 'status', 'visibility']
    ordering_fields = ['order', 'name']
    ordering = ['order']
    
    def get_organizer(self):
        """Obtener el organizador asociado al usuario actual."""
        try:
            organizer_user = OrganizerUser.objects.get(user=self.request.user)
            return organizer_user.organizer
        except OrganizerUser.DoesNotExist:
            return None
    
    def get_queryset(self):
        """
        Get ticket categories based on permissions.
        """
        # For public access, only return public categories for active events
        if not self.request.user.is_authenticated:
            return TicketCategory.objects.filter(
                event__status='active',
                event__visibility='public',
                visibility='public'
            )
        
        # For organizers, return all their categories
        organizer = self.get_organizer()
        if not organizer:
            return TicketCategory.objects.none()
        
        # Check for event_id in URL or query params
        event_id = self.kwargs.get('event_id')
        if not event_id:
            event_id = self.request.query_params.get('event')
        
        queryset = TicketCategory.objects.filter(event__organizer=organizer)
        if event_id:
            queryset = queryset.filter(event_id=event_id)
        return queryset
    
    def get_permissions(self):
        """
        Get permissions based on action.
        """
        print(f"DEBUG - TicketCategoryViewSet.get_permissions - action: {self.action}")
        print(f"DEBUG - TicketCategoryViewSet.get_permissions - user: {self.request.user.id if self.request.user.is_authenticated else 'Anonymous'}")
        
        if self.action in ['list', 'retrieve']:
            print(f"DEBUG - TicketCategoryViewSet.get_permissions - permissions: AllowAny (list/retrieve)")
            return [permissions.AllowAny()]
            
        # Simplificar permisos - la verificación real se hace en los métodos del ViewSet
        print(f"DEBUG - TicketCategoryViewSet.get_permissions - simplified permissions: IsAuthenticated only")
        return [permissions.IsAuthenticated()]
    
    def perform_create(self, serializer):
        """Create a new ticket category with the event ID from the URL or request data."""
        # Check if this is a nested view (event_id in URL)
        event_id = self.kwargs.get('event_id')
        
        if event_id:
            # This is a nested view, get event from URL
            event = get_object_or_404(Event, id=event_id)
            serializer.save(event=event)
        else:
            # This is a standalone/top-level view
            # Get event_id from request data
            event_id = self.request.data.get('event')
            
            if not event_id:
                raise serializers.ValidationError({"event": "Event ID is required to create a ticket category"})
                
            # Get the event instance
            event = get_object_or_404(Event, id=event_id)
            
            # Check if the event belongs to the organizer
            organizer = self.get_organizer()
            if not organizer or event.organizer != organizer:
                raise PermissionDenied("You don't have permission to add ticket categories to this event.")
            
            # Create the ticket category with the event
            serializer.save(event=event)
            
    def update(self, request, *args, **kwargs):
        """Override update to use OrganizerUser for permission checks."""
        print(f"DEBUG - TicketCategoryViewSet.update - Starting update for ID: {kwargs.get('pk')}")
        
        # Get the category being updated
        instance = self.get_object()
        
        # Get the organizer associated with the user
        organizer = self.get_organizer()
        if not organizer:
            return Response(
                {"detail": "You don't have permission to update this category as you are not associated with any organizer."},
                status=status.HTTP_403_FORBIDDEN
            )
            
        # Check if the event belongs to the organizer
        if instance.event.organizer != organizer:
            return Response(
                {"detail": "You don't have permission to update this category as it belongs to another organizer."},
                status=status.HTTP_403_FORBIDDEN
            )
                
        # Permission check passed, proceed with update
        return super().update(request, *args, **kwargs)
        
    def partial_update(self, request, *args, **kwargs):
        """Override partial_update to use OrganizerUser for permission checks."""
        print(f"DEBUG - TicketCategoryViewSet.partial_update - Starting partial update for ID: {kwargs.get('pk')}")
        return self.update(request, *args, **kwargs)
        
    def destroy(self, request, *args, **kwargs):
        """Override destroy to use OrganizerUser for permission checks."""
        print(f"DEBUG - TicketCategoryViewSet.destroy - Starting delete for ID: {kwargs.get('pk')}")
        
        # Get the category being deleted
        instance = self.get_object()
        
        # Get the organizer associated with the user
        organizer = self.get_organizer()
        if not organizer:
            return Response(
                {"detail": "You don't have permission to delete this category as you are not associated with any organizer."},
                status=status.HTTP_403_FORBIDDEN
            )
            
        # Check if the event belongs to the organizer
        if instance.event.organizer != organizer:
            return Response(
                {"detail": "You don't have permission to delete this category as it belongs to another organizer."},
                status=status.HTTP_403_FORBIDDEN
            )
                
        # Permission check passed, proceed with delete
        return super().destroy(request, *args, **kwargs)


class TicketTierViewSet(viewsets.ModelViewSet):
    """Viewset for ticket tiers."""
    serializer_class = TicketTierSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_organizer(self):
        """Obtener el organizador asociado al usuario actual."""
        try:
            organizer_user = OrganizerUser.objects.get(user=self.request.user)
            return organizer_user.organizer
        except OrganizerUser.DoesNotExist:
            return None
    
    def get_queryset(self):
        """Filter queryset by organizer and event_id if provided"""
        organizer = self.get_organizer()
        print(f"DEBUG - TicketTierViewSet.get_queryset - User ID: {self.request.user.id}, Organizer: {organizer.id if organizer else 'None'}")
        
        if not organizer:
            print(f"DEBUG - TicketTierViewSet.get_queryset - No organizer found for user")
            return TicketTier.objects.none()
        
        # If this is a nested view under an event, filter by the event_id from URL
        event_id = self.kwargs.get('event_id')
        
        # If it's a standalone view, check for event query parameter
        if not event_id and self.request.query_params.get('event'):
            event_id = self.request.query_params.get('event')
            print(f"DEBUG - TicketTierViewSet.get_queryset - Using event query parameter: {event_id}")
        
        if event_id:
            print(f"DEBUG - TicketTierViewSet.get_queryset - Filtering by event ID: {event_id}")
            return TicketTier.objects.filter(
                event__organizer=organizer,
                event_id=event_id
            )
        
        # For top-level view without event filter, return all tiers for the organizer's events
        print(f"DEBUG - TicketTierViewSet.get_queryset - No event filter, returning all tiers for organizer")
        return TicketTier.objects.filter(event__organizer=organizer)
    
    def update(self, request, *args, **kwargs):
        """Override update to add detailed permission checks logging."""
        print(f"DEBUG - TicketTierViewSet.update - Starting update for ID: {kwargs.get('pk')}")
        print(f"DEBUG - User ID: {request.user.id}, Username: {request.user.username}")
        
        # Get the organizer associated with the user
        try:
            organizer_user = OrganizerUser.objects.get(user=request.user)
            organizer = organizer_user.organizer
            print(f"DEBUG - Found organizer: ID={organizer.id}")
            
            # Get the tier being updated
            instance = self.get_object()
            print(f"DEBUG - Ticket tier belongs to event ID: {instance.event.id}")
            print(f"DEBUG - Event organizer ID: {instance.event.organizer.id}")
            
            # Check if the organizer owns the event
            if instance.event.organizer != organizer:
                print(f"DEBUG - PERMISSION DENIED: Ticket tier's event organizer ({instance.event.organizer.id}) does not match user's organizer ({organizer.id})")
                return Response(
                    {"detail": "You don't have permission to update this ticket tier as it belongs to another organizer."},
                    status=status.HTTP_403_FORBIDDEN
                )
                
            # Extract price from data if it's a structured object
            if 'price' in request.data and isinstance(request.data['price'], dict):
                price_data = request.data['price'].get('basePrice', 0)
                print(f"DEBUG - Extracted price from object: {price_data}")
                
                # Create new data with extracted price
                modified_data = request.data.copy()
                modified_data['price'] = price_data
                
                # Get serializer with modified data
                serializer = self.get_serializer(instance, data=modified_data, partial=kwargs.get('partial', False))
                serializer.is_valid(raise_exception=True)
                self.perform_update(serializer)
                
                return Response(serializer.data)
            
            # Default behavior if price is not a structured object
            print(f"DEBUG - Permission check passed, proceeding with update")
            return super().update(request, *args, **kwargs)
            
        except OrganizerUser.DoesNotExist:
            print(f"DEBUG - PERMISSION DENIED: User {request.user.id} is not associated with any organizer")
            return Response(
                {"detail": "You don't have permission to update this ticket tier as you are not associated with any organizer."},
                status=status.HTTP_403_FORBIDDEN
            )
        except Exception as e:
            print(f"DEBUG - Error during permission check: {str(e)}")
            return Response(
                {"detail": f"Error checking permissions: {str(e)}"},
                status=status.HTTP_403_FORBIDDEN
            )
    
    def partial_update(self, request, *args, **kwargs):
        """Override partial_update to add detailed permission checks logging."""
        print(f"DEBUG - TicketTierViewSet.partial_update - Starting partial update for ID: {kwargs.get('pk')}")
        
        # Handle structured price the same way as in update
        if 'price' in request.data and isinstance(request.data['price'], dict):
            # Set partial=True to ensure partial update
            kwargs['partial'] = True
        
        return self.update(request, *args, **kwargs)
    
    def perform_create(self, serializer):
        """Create a ticket tier, with event_id if provided in URL"""
        # Get the event from the URL if this is a nested view
        event_id = self.kwargs.get('event_id')
        if event_id:
            print(f"DEBUG - TicketTierViewSet.perform_create - Creating ticket tier with event ID from URL: {event_id}")
            event = get_object_or_404(Event, id=event_id)
            
            # Check if the event belongs to the organizer
            organizer = self.get_organizer()
            if not organizer or event.organizer != organizer:
                print(f"DEBUG - PERMISSION DENIED: Event organizer ({event.organizer.id}) does not match user's organizer ({organizer.id if organizer else 'None'})")
                raise PermissionDenied("You don't have permission to add ticket tiers to this event.")
            
            # 🚀 ENTERPRISE FIX: Handle price properly regardless of format
            price_data = self.request.data.get('price', 0)
            if isinstance(price_data, dict):
                price_data = price_data.get('basePrice', 0)
                print(f"DEBUG - Extracted price from object: {price_data}")
            elif price_data is None:
                price_data = 0
                print(f"DEBUG - Price was None, using default: {price_data}")
            else:
                print(f"DEBUG - Using direct price value: {price_data}")
                
            # Get capacity to set available field
            capacity = self.request.data.get('capacity', 0)
            print(f"DEBUG - Using capacity value for available: {capacity}")
            
            # Save with extracted price value and set available = capacity
            serializer.save(event=event, price=price_data, available=capacity)
        else:
            # Extract event ID from request data for top-level view
            event_id = self.request.data.get('event')
            print(f"DEBUG - TicketTierViewSet.perform_create - Creating ticket tier with event ID from request data: {event_id}")
            
            if not event_id:
                print(f"DEBUG - TicketTierViewSet.perform_create - FAIL: No event ID in request data")
                raise serializers.ValidationError({"event": "Event ID is required to create a ticket tier"})
                
            # Get the event instance
            event = get_object_or_404(Event, id=event_id)
            
            # Check if the event belongs to the organizer
            organizer = self.get_organizer()
            if not organizer or event.organizer != organizer:
                print(f"DEBUG - PERMISSION DENIED: Event organizer ({event.organizer.id}) does not match user's organizer ({organizer.id if organizer else 'None'})")
                raise PermissionDenied("You don't have permission to add ticket tiers to this event.")
            
            # 🚀 ENTERPRISE FIX: Handle price properly regardless of format
            price_data = self.request.data.get('price', 0)
            if isinstance(price_data, dict):
                price_data = price_data.get('basePrice', 0)
                print(f"DEBUG - Extracted price from object: {price_data}")
            elif price_data is None:
                price_data = 0
                print(f"DEBUG - Price was None, using default: {price_data}")
            else:
                print(f"DEBUG - Using direct price value: {price_data}")
                
            # Get capacity to set available field
            capacity = self.request.data.get('capacity', 0)
            print(f"DEBUG - Using capacity value for available: {capacity}")
            
            # Save with extracted price value and set available = capacity
            serializer.save(event=event, price=price_data, available=capacity)

    @action(detail=True, methods=['post'])
    def form_link(self, request, pk=None):
        """Link a form to a ticket tier"""
        ticket_tier = self.get_object()
        form_id = request.data.get('form_id')
        
        if not form_id:
            return Response(
                {"detail": "Form ID is required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            form = Form.objects.get(id=form_id)
            
            # Get the organizer properly
            organizer = self.get_organizer()
            
            # Verify the form belongs to the same organizer
            if form.organizer != organizer:
                return Response(
                    {"detail": "You don't have permission to use this form"}, 
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Update the ticket tier with the form directly
            ticket_tier.form = form
            ticket_tier.save()
            
            return Response({
                "id": ticket_tier.id,
                "name": ticket_tier.name,
                "form_id": form_id,
                "form_name": form.name
            })
            
        except Form.DoesNotExist:
            return Response(
                {"detail": "Form not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {"detail": str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def category_link(self, request, pk=None):
        """Link a category to a ticket tier"""
        ticket_tier = self.get_object()
        category_id = request.data.get('category_id')
        
        if not category_id:
            return Response(
                {"detail": "Category ID is required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            category = TicketCategory.objects.get(id=category_id)
            
            # Get the organizer properly
            organizer = self.get_organizer()
            
            # Verify the category belongs to the same organizer and event
            if category.event.organizer != organizer:
                return Response(
                    {"detail": "You don't have permission to use this category"}, 
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Verify the category belongs to the same event as the ticket tier
            if category.event != ticket_tier.event:
                return Response(
                    {"detail": "Category must belong to the same event as the ticket tier"}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Update the ticket tier with the category directly
            ticket_tier.category = category
            ticket_tier.save()
            
            return Response({
                "id": ticket_tier.id,
                "name": ticket_tier.name,
                "category_id": category_id,
                "category_name": category.name
            })
            
        except TicketCategory.DoesNotExist:
            return Response(
                {"detail": "Category not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {"detail": str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )



    
    @action(detail=False, methods=['get'])
    def types(self, request):
        """
        Get available field types and their configurations.
        """
        field_types = [
            {
                'value': 'text',
                'label': 'Texto corto',
                'supportsRequired': True,
                'supportsPlaceholder': True,
                'supportsHelpText': True,
                'supportsValidation': True,
                'validations': ['minLength', 'maxLength', 'pattern']
            },
            {
                'value': 'textarea',
                'label': 'Texto largo',
                'supportsRequired': True,
                'supportsPlaceholder': True,
                'supportsHelpText': True,
                'supportsValidation': True,
                'validations': ['minLength', 'maxLength']
            },
            {
                'value': 'email',
                'label': 'Email',
                'supportsRequired': True,
                'supportsPlaceholder': True,
                'supportsHelpText': True,
                'supportsValidation': False
            },
            {
                'value': 'phone',
                'label': 'Teléfono',
                'supportsRequired': True,
                'supportsPlaceholder': True,
                'supportsHelpText': True,
                'supportsValidation': False
            },
            {
                'value': 'number',
                'label': 'Número',
                'supportsRequired': True,
                'supportsPlaceholder': True,
                'supportsHelpText': True,
                'supportsValidation': True,
                'validations': ['min', 'max']
            },
            {
                'value': 'select',
                'label': 'Lista desplegable',
                'supportsRequired': True,
                'supportsPlaceholder': True,
                'supportsHelpText': True,
                'supportsOptions': True,
                'supportsValidation': False
            },
            {
                'value': 'checkbox',
                'label': 'Casillas de verificación',
                'supportsRequired': True,
                'supportsHelpText': True,
                'supportsOptions': True,
                'supportsValidation': False
            },
            {
                'value': 'radio',
                'label': 'Opciones únicas',
                'supportsRequired': True,
                'supportsHelpText': True,
                'supportsOptions': True,
                'supportsValidation': False
            },
            {
                'value': 'date',
                'label': 'Fecha',
                'supportsRequired': True,
                'supportsHelpText': True,
                'supportsValidation': False
            },
            {
                'value': 'heading',
                'label': 'Título',
                'supportsRequired': False,
                'supportsHelpText': False,
                'supportsValidation': False
            },
            {
                'value': 'paragraph',
                'label': 'Párrafo',
                'supportsRequired': False,
                'supportsHelpText': True,
                'supportsValidation': False
            }
        ]
        
        width_options = [
            {'value': 'full', 'label': 'Completo'},
            {'value': 'half', 'label': 'Medio'},
            {'value': 'third', 'label': 'Un tercio'}
        ]
        
        conditional_operators = [
            {'value': 'equals', 'label': 'Es igual a'},
            {'value': 'notEquals', 'label': 'No es igual a'},
            {'value': 'contains', 'label': 'Contiene'},
            {'value': 'notContains', 'label': 'No contiene'},
            {'value': 'greaterThan', 'label': 'Mayor que'},
            {'value': 'lessThan', 'label': 'Menor que'}
        ]
        
        return Response({
            'fieldTypes': field_types,
            'widthOptions': width_options,
            'conditionalOperators': conditional_operators
        })


class OrderViewSet(viewsets.ModelViewSet):
    """
    API endpoint for orders.
    """
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['event', 'status', 'payment_method']
    search_fields = ['order_number', 'first_name', 'last_name', 'email']
    ordering_fields = ['created_at', 'updated_at', 'total']
    ordering = ['-created_at']
    
    def get_organizer(self):
        """Obtener el organizador asociado al usuario actual."""
        try:
            organizer_user = OrganizerUser.objects.get(user=self.request.user)
            return organizer_user.organizer
        except OrganizerUser.DoesNotExist:
            return None
    
    def get_serializer_class(self):
        """
        Return appropriate serializer class.
        """
        if self.action == 'retrieve':
            return OrderDetailSerializer
        return OrderSerializer
    
    def get_queryset(self):
        """
        Get orders based on permissions with STRICT event isolation.
        🚀 ENTERPRISE: Multi-level filtering to prevent data leakage between events.
        """
        # Regular users can only see their own orders
        if self.request.user.is_authenticated and not hasattr(self.request.user, 'organizer_roles'):
            return Order.objects.filter(user=self.request.user)
        
        # 🚀 ENTERPRISE: Organizers can see orders for their events with STRICT isolation
        if self.request.user.is_authenticated:
            organizer = self.get_organizer()
            if organizer:
                # 🚨 CRITICAL: Event ID is MANDATORY for security
                event_id = self.request.query_params.get('event_id')
                if not event_id:
                    # 🚨 SECURITY: Without event_id, return empty to prevent data leakage
                    return Order.objects.none()
                
                # 🚀 ENTERPRISE: Multi-level filtering for maximum security
                queryset = Order.objects.filter(
                    event__organizer=organizer,
                    event_id=event_id  # ← STRICT event isolation
                )
                
                # 🚨 SECURITY: Additional validation - ensure event belongs to organizer
                event = Event.objects.filter(id=event_id, organizer=organizer).first()
                if not event:
                    return Order.objects.none()
                
                return queryset
        
        # No orders for unauthenticated users
        return Order.objects.none()
    
    @action(detail=True, methods=['post'])
    def refund(self, request, pk=None):
        """
        Refund an order.
        """
        order = self.get_object()
        
        # Check if order can be refunded
        if order.status != 'paid':
            return Response(
                {"detail": "Only paid orders can be refunded."},
                status=status.HTTP_400_BAD_REQUEST)
        
        # Get reason from request data
        reason = request.data.get('reason', '')
        amount = request.data.get('amount', order.total)
        
        # In a real app, you would process the refund with a payment gateway here
        
        # Update order status
        order.status = 'refunded'
        order.refund_reason = reason
        order.refunded_amount = amount
        order.save()
        
        # Update tickets status
        for item in order.items.all():
            for ticket in item.tickets.all():
                ticket.status = 'refunded'
                ticket.save()
        
        return Response({"detail": "Order refunded successfully."})
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """
        Cancel an order.
        """
        order = self.get_object()
        
        # Check if order can be cancelled
        if order.status not in ['pending', 'paid']:
            return Response(
                {"detail": "Only pending or paid orders can be cancelled."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get reason from request data
        reason = request.data.get('reason', '')
        
        # Update order status
        order.status = 'cancelled'
        order.notes = f"{order.notes}\nCancelled: {reason}".strip()
        order.save()
        
        # Update tickets status
        for item in order.items.all():
            for ticket in item.tickets.all():
                ticket.status = 'cancelled'
                ticket.save()
        
        return Response({"detail": "Order cancelled successfully."})


class TicketViewSet(viewsets.ModelViewSet):
    """
    API endpoint for tickets.
    """
    serializer_class = TicketSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'checked_in']
    search_fields = ['ticket_number', 'first_name', 'last_name', 'email']
    ordering_fields = ['first_name', 'last_name', 'check_in_time']
    ordering = ['first_name', 'last_name']
    
    def get_organizer(self):
        """Obtener el organizador asociado al usuario actual."""
        try:
            organizer_user = OrganizerUser.objects.get(user=self.request.user)
            return organizer_user.organizer
        except OrganizerUser.DoesNotExist:
            return None
    
    def get_queryset(self):
        """
        Get tickets based on permissions with STRICT event isolation.
        🚀 ENTERPRISE: Multi-level filtering to prevent data leakage between events.
        """
        # Regular users can only see their own tickets
        if self.request.user.is_authenticated and not hasattr(self.request.user, 'organizer_roles'):
            return Ticket.objects.filter(order_item__order__user=self.request.user)
        
        # 🚀 ENTERPRISE: Organizers can see tickets for their events with STRICT isolation
        if self.request.user.is_authenticated:
            organizer = self.get_organizer()
            if organizer:
                # 🚨 CRITICAL: Event ID is MANDATORY for security
                event_id = self.request.query_params.get('event_id')
                if not event_id:
                    # 🚨 SECURITY: Without event_id, return empty to prevent data leakage
                    return Ticket.objects.none()
                
                # 🚀 ENTERPRISE: Multi-level filtering for maximum security
                queryset = Ticket.objects.filter(
                    order_item__order__event__organizer=organizer,
                    order_item__order__event_id=event_id  # ← STRICT event isolation
                )
                
                # 🚨 SECURITY: Additional validation - ensure event belongs to organizer
                event = Event.objects.filter(id=event_id, organizer=organizer).first()
                if not event:
                    return Ticket.objects.none()
                
                return queryset
        
        # No tickets for unauthenticated users
        return Ticket.objects.none()
    
    @action(detail=True, methods=['post'])
    def check_in(self, request, pk=None):
        """
        Check in a ticket.
        """
        ticket = self.get_object()
        
        # Check if ticket can be checked in
        if ticket.status != 'active':
            return Response(
                {"detail": "Only active tickets can be checked in."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if ticket.checked_in:
            return Response(
                {"detail": "Ticket already checked in."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update ticket status
        ticket.checked_in = True
        ticket.check_in_time = timezone.now()
        ticket.status = 'used'
        ticket.save()
        
        return Response({
            "detail": "Ticket checked in successfully.",
            "ticket": TicketSerializer(ticket).data
        })
    
    @action(detail=True, methods=['post'])
    def validate(self, request, pk=None):
        """
        Validate a ticket by number.
        """
        ticket_number = request.data.get('ticket_number')
        
        if not ticket_number:
            return Response(
                {"detail": "Ticket number is required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Get organizer properly
            organizer = self.get_organizer()
            if not organizer:
                return Response({
                    "is_valid": False,
                    "detail": "Usuario sin organizador asociado"
                })
            
            # Find ticket by number, ensuring it belongs to the organizer's events
            ticket = Ticket.objects.get(
                ticket_number=ticket_number,
                order_item__order__event__organizer=organizer
            )
            
            # Check ticket status
            if ticket.status != 'active':
                return Response({
                    "is_valid": False,
                    "detail": f"Ticket is not active. Current status: {ticket.get_status_display()}"
                })
            
            if ticket.checked_in:
                return Response({
                    "is_valid": False,
                    "detail": f"Ticket already checked in at {ticket.check_in_time}"
                })
            
            # Return ticket details
            return Response({
                "is_valid": True,
                "ticket": TicketSerializer(ticket).data
            })
            
        except Ticket.DoesNotExist:
            return Response({
                "is_valid": False,
                "detail": "Invalid ticket number"
            })
    
    @action(detail=True, methods=['get'])
    def form(self, request, pk=None):
        """
        Get the form fields for a ticket with conditional logic applied.
        """
        ticket = self.get_object()
        
        # Get the form associated with the ticket tier
        ticket_tier = ticket.order_item.ticket_tier
        form = ticket_tier.form
        
        if not form:
            return Response({
                "detail": "No form associated with this ticket."
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get existing data from the ticket
        existing_data = ticket.form_data or {}
        
        # Get all fields from the form
        all_fields = form.fields.all().order_by('order')
        
        # Process fields to apply conditional logic
        visible_fields = []
        for field in all_fields:
            # Check if field should be visible based on conditional rules
            if self.should_display_field(field, existing_data):
                field_data = FormFieldSerializer(field).data
                field_data['current_value'] = existing_data.get(field.id, '')
                visible_fields.append(field_data)
        
        form_data = {
            'id': form.id,
            'name': form.name,
            'description': form.description,
            'fields': visible_fields,
        }
        
        return Response(form_data)
    
    def should_display_field(self, field, form_data):
        """
        Determine if a field should be displayed based on conditional logic.
        
        Args:
            field: FormField instance
            form_data: Dictionary with existing form data, where keys are field IDs
            
        Returns:
            Boolean indicating if field should be displayed
        """
        # If no conditional display rules, field is always shown
        if not field.conditional_display:
            return True
        
        # Field is only shown if ALL rules are satisfied
        for rule in field.conditional_display:
            source_field_id = rule.get('sourceField')
            condition = rule.get('condition')
            expected_value = rule.get('value')
            
            # If rule is incomplete, ignore it
            if not all([source_field_id, condition, expected_value is not None]):
                continue
            
            # Get actual value from form data
            actual_value = form_data.get(source_field_id, '')
            
            # Apply the condition
            if condition == 'equals' and str(actual_value) != str(expected_value):
                return False
            elif condition == 'notEquals' and str(actual_value) == str(expected_value):
                return False
            elif condition == 'contains' and str(expected_value) not in str(actual_value):
                return False
            elif condition == 'notContains' and str(expected_value) in str(actual_value):
                return False
            elif condition == 'greaterThan':
                try:
                    if float(actual_value) <= float(expected_value):
                        return False
                except (ValueError, TypeError):
                    return False
            elif condition == 'lessThan':
                try:
                    if float(actual_value) >= float(expected_value):
                        return False
                except (ValueError, TypeError):
                    return False
        
        # All rules passed
        return True
    
    @action(detail=True, methods=['post'])
    def submit_form(self, request, pk=None):
        """
        Submit form data for a ticket.
        """
        ticket = self.get_object()
        form_data = request.data.get('form_data', {})
        
        # Validate form data against form schema
        if ticket.order_item.ticket_tier.form:
            form = ticket.order_item.ticket_tier.form
            fields = form.fields.all()
            
            # Check required fields
            for field in fields:
                # Skip conditional fields that shouldn't be visible
                if not self.should_display_field(field, form_data):
                    continue
                    
                field_id = str(field.id)
                if field.required and (field_id not in form_data or not form_data[field_id]):
                    return Response({
                        "detail": f"Field '{field.label}' is required."
                    }, status=status.HTTP_400_BAD_REQUEST)
            
            # Store the form data on the ticket
            ticket.form_data = form_data
            ticket.save()
            
            return Response({
                "detail": "Form data saved successfully.",
                "ticket": TicketSerializer(ticket).data
            })
        
        return Response({
            "detail": "No form associated with this ticket."
        }, status=status.HTTP_400_BAD_REQUEST)


class CouponViewSet(viewsets.ModelViewSet):
    """
    API endpoint for coupons.
    """
    serializer_class = CouponSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active', 'status', 'discount_type']
    search_fields = ['code', 'description']
    ordering_fields = ['code', 'discount_value', 'created_at', 'usage_count']
    ordering = ['-created_at']
    
    def get_organizer(self):
        """Obtener el organizador asociado al usuario actual."""
        try:
            organizer_user = OrganizerUser.objects.get(user=self.request.user)
            return organizer_user.organizer
        except OrganizerUser.DoesNotExist:
            return None
    
    def get_queryset(self):
        """
        Get coupons for the current organizer with STRICT event isolation.
        🚀 ENTERPRISE: Multi-level filtering to prevent data leakage between events.
        """
        if not self.request.user.is_authenticated:
            print(f"🔒 DEBUG - CouponViewSet.get_queryset: User not authenticated")
            return Coupon.objects.none()
        
        organizer = self.get_organizer()
        if not organizer:
            print(f"🔒 DEBUG - CouponViewSet.get_queryset: No organizer found")
            return Coupon.objects.none()
        
        print(f"🔒 DEBUG - CouponViewSet.get_queryset: Organizer: {organizer.id} ({organizer.name})")
        
        # 🚨 CRITICAL: Event ID is MANDATORY for security
        event_id = self.request.query_params.get('event_id')
        print(f"🔒 DEBUG - CouponViewSet.get_queryset: Event ID from query: {event_id}")
        
        if not event_id:
            print(f"🔒 DEBUG - CouponViewSet.get_queryset: No event_id provided, returning empty")
            # 🚨 SECURITY: Without event_id, return empty to prevent data leakage
            return Coupon.objects.none()
        
        # 🚨 SECURITY: Additional validation - ensure event belongs to organizer
        event = Event.objects.filter(id=event_id, organizer=organizer).first()
        if not event:
            print(f"🔒 DEBUG - CouponViewSet.get_queryset: Event {event_id} not found or not owned by organizer")
            return Coupon.objects.none()
        
        print(f"🔒 DEBUG - CouponViewSet.get_queryset: Event validated: {event.id} ({event.title})")
        
        # 🚀 ENTERPRISE: Multi-level filtering for maximum security
        base_queryset = Coupon.objects.filter(organizer=organizer)
        print(f"🔒 DEBUG - CouponViewSet.get_queryset: Base queryset (organizer only): {base_queryset.count()} coupons")
        
        # 🚀 ENTERPRISE: Simplified Global vs Local filtering
        # Global coupons (null events_list = all events)
        global_coupons = base_queryset.filter(events_list__isnull=True)
        print(f"🔒 DEBUG - CouponViewSet.get_queryset: Global coupons: {global_coupons.count()}")
        
        # Local coupons (events_list contains current event)
        local_coupons = base_queryset.filter(events_list__contains=[event_id])
        print(f"🔒 DEBUG - CouponViewSet.get_queryset: Local coupons: {local_coupons.count()}")
        
        # Combine both types
        final_queryset = base_queryset.filter(
            Q(events_list__isnull=True) |  # Global
            Q(events_list__contains=[event_id])  # Local
        ).distinct()
        
        print(f"🔒 DEBUG - CouponViewSet.get_queryset: Final queryset: {final_queryset.count()} coupons")
        
        # Log each coupon for debugging
        for coupon in final_queryset:
            print(f"🔒 DEBUG - Coupon: {coupon.code} (ID: {coupon.id}) - {coupon}")
            print(f"  - events_list: {coupon.events_list}")
            print(f"  - organizer: {coupon.organizer_id}")
            print(f"  - is_global: {coupon.is_global}")
            print(f"  - is_local: {coupon.is_local}")
            print(f"  - applicable_event_id: {coupon.applicable_event_id}")
        
        return final_queryset
    
    def get_object(self):
        """
        🚀 ENTERPRISE: Override get_object to handle individual coupon operations (GET, PUT, DELETE)
        without requiring event_id in query params.
        """
        # Get the coupon by ID first
        coupon_id = self.kwargs.get('pk')
        if not coupon_id:
            raise Http404("Coupon ID is required")
        
        try:
            # Find coupon by ID and organizer (security check)
            organizer = self.get_organizer()
            if not organizer:
                raise Http404("Organizer not found")
            
            coupon = Coupon.objects.get(id=coupon_id, organizer=organizer)
            
            # 🚨 SECURITY: Additional validation - ensure user can access this coupon
            # For individual operations, we don't need event_id validation
            # The organizer check is sufficient for security
            
            return coupon
            
        except Coupon.DoesNotExist:
            raise Http404("Coupon not found")
    
    def perform_create(self, serializer):
        """
        Create a new coupon for the current organizer.
        """
        organizer = self.get_organizer()
        if not organizer:
            raise serializers.ValidationError({"detail": "El usuario no tiene un organizador asociado"})
            
        serializer.save(organizer=organizer)
    
    @action(detail=False, methods=['post'])
    def validate(self, request):
        """
        Validate a coupon code.
        """
        code = request.data.get('code')
        event_id = request.data.get('event_id')
        
        if not code or not event_id:
            return Response(
                {"detail": "Coupon code and event ID are required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Find coupon by code
            organizer = self.get_organizer()
            if not organizer:
                return Response({
                    "is_valid": False,
                    "detail": "Usuario sin organizador asociado"
                })
                
            coupon = Coupon.objects.get(code=code, organizer=organizer)
            
            # Check if coupon is active
            if not coupon.is_active:
                return Response({
                    "is_valid": False,
                    "detail": "Coupon is not active."
                })
            
            # Check usage limits
            if coupon.usage_limit and coupon.usage_count >= coupon.usage_limit:
                return Response({
                    "is_valid": False,
                    "detail": "Coupon usage limit has been reached."
                })
            
            # Check date validity
            now = timezone.now()
            if coupon.start_date and now < coupon.start_date:
                return Response({
                    "is_valid": False,
                    "detail": "Coupon is not yet valid."
                })
            
            if coupon.end_date and now > coupon.end_date:
                return Response({
                    "is_valid": False,
                    "detail": "Coupon has expired."
                })
            
            # Check event applicability
            events_list = coupon.get_applicable_events()
            if events_list is not None and str(event_id) not in events_list:
                return Response({
                    "is_valid": False,
                    "detail": "Coupon is not valid for this event."
                })
            
            # Return coupon details
            return Response({
                "is_valid": True,
                "coupon": CouponSerializer(coupon).data
            })
            
        except Coupon.DoesNotExist:
            return Response({
                "is_valid": False,
                "detail": "Coupon not found."
            })
    
    @action(detail=True, methods=['post'])
    def toggle_active(self, request, pk=None):
        """
        Toggle the active status of a coupon.
        """
        coupon = self.get_object()
        coupon.is_active = not coupon.is_active
        coupon.save()
        
        return Response({
            "detail": f"Coupon is now {'active' if coupon.is_active else 'inactive'}.",
            "coupon": CouponSerializer(coupon).data
        })
    
    @action(detail=False, methods=['get'])
    def analytics(self, request):
        """
        Get analytics data for coupons.
        """
        # Get organizer properly
        organizer = self.get_organizer()
        if not organizer:
            return Response({
                "detail": "Usuario sin organizador asociado"
            }, status=status.HTTP_400_BAD_REQUEST)
            
        # Get coupons for this organizer
        coupons = Coupon.objects.filter(organizer=organizer)
        
        # Calculate stats
        total_coupons = coupons.count()
        active_coupons = coupons.filter(is_active=True).count()
        
        # Calculate redemptions
        total_redemptions = coupons.aggregate(total=Sum('usage_count'))['total'] or 0
        
        # Calculate redemption rate
        total_possible = coupons.aggregate(
            total=Sum(F('usage_limit'))
        )['total'] or 0
        
        redemption_rate = 0
        if total_possible > 0:
            redemption_rate = round((total_redemptions / total_possible) * 100)
        
        # Calculate total savings (this is an estimate)
        # For percentage coupons, we'll need order data to calculate actual savings
        
        # Get recent coupons
        recent_coupons = coupons.order_by('-created_at')[:5]
        
        # Get most used coupons
        most_used = coupons.order_by('-usage_count')[:5]
        
        # Compile analytics data
        data = {
            'total_coupons': total_coupons,
            'active_coupons': active_coupons,
            'total_redemptions': total_redemptions,
            'redemption_rate': redemption_rate,
            'recent_coupons': CouponSerializer(recent_coupons, many=True).data,
            'most_used_coupons': CouponSerializer(most_used, many=True).data
        }
        
        return Response(data)


class EventCommunicationViewSet(viewsets.ModelViewSet):
    """
    API endpoint for event communications.
    """
    serializer_class = EventCommunicationSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['event', 'type', 'status']
    search_fields = ['name', 'subject', 'content']
    ordering_fields = ['name', 'scheduled_date', 'created_at']
    ordering = ['-created_at']
    
    def get_organizer(self):
        """Obtener el organizador asociado al usuario actual."""
        try:
            organizer_user = OrganizerUser.objects.get(user=self.request.user)
            return organizer_user.organizer
        except OrganizerUser.DoesNotExist:
            return None
    
    def get_queryset(self):
        """
        Get communications for events belonging to the current organizer.
        """
        if not self.request.user.is_authenticated:
            return EventCommunication.objects.none()
        
        organizer = self.get_organizer()
        if not organizer:
            return EventCommunication.objects.none()
        
        return EventCommunication.objects.filter(
            event__organizer=organizer
        )
    
    @action(detail=True, methods=['post'])
    def send(self, request, pk=None):
        """
        Send a communication.
        """
        communication = self.get_object()
        
        # Check if communication can be sent
        if communication.status not in ['draft', 'scheduled']:
            return Response(
                {"detail": "Only draft or scheduled communications can be sent."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # In a real app, you would send the communication here
        # For now, we'll just update the status
        communication.status = 'sent'
        communication.sent_date = timezone.now()
        communication.save()
        
        return Response({"detail": "Communication sent successfully."})
    
    @action(detail=True, methods=['post'])
    def schedule(self, request, pk=None):
        """
        Schedule a communication.
        """
        communication = self.get_object()
        scheduled_date = request.data.get('scheduled_date')
        
        if not scheduled_date:
            return Response(
                {"detail": "Scheduled date is required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if communication can be scheduled
        if communication.status != 'draft':
            return Response(
                {"detail": "Only draft communications can be scheduled."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update communication status
        communication.status = 'scheduled'
        communication.scheduled_date = scheduled_date
        communication.save()
        
        return Response({"detail": "Communication scheduled successfully."}) 