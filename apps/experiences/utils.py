"""
Utility functions for experiences app.
"""

from datetime import datetime, timedelta, time as dt_time
from django.utils import timezone
from django.db import transaction
import logging

from .models import Experience, TourInstance

logger = logging.getLogger(__name__)


def generate_tour_instances_from_pattern(experience: Experience):
    """
    🚀 ENTERPRISE: Generate tour instances from recurrence pattern.
    
    Generates TourInstance objects based on the experience's recurrence_pattern
    within the booking_horizon_days window.
    
    Soporta dos formatos:
    1. weekly_schedule (formato del flujo real): { schema_version: 1, weekly_schedule: { monday: [...], ... } }
    2. Legacy format: { pattern: 'daily', times: [...], days_of_week: [...], start_date: '...' }
    
    Args:
        experience: Experience instance with recurrence_pattern configured
        
    Returns:
        int: Number of instances created
    """
    if not experience.recurrence_pattern:
        logger.warning(
            f"⚠️ [INSTANCE_GENERATION] Experience {experience.id} has no recurrence_pattern"
        )
        return 0
    
    pattern = experience.recurrence_pattern
    
    # Get booking horizon
    booking_horizon_days = experience.booking_horizon_days or 90
    today = timezone.now().date()
    horizon_end = today + timedelta(days=booking_horizon_days)
    
    # Get existing instances to avoid duplicates
    existing_instances = TourInstance.objects.filter(
        experience=experience,
        status='active'
    ).values_list('start_datetime', 'language')
    
    existing_keys = {
        (inst[0].isoformat() if isinstance(inst[0], datetime) else str(inst[0]), inst[1])
        for inst in existing_instances
    }
    
    instances_created = 0
    
    # Formato weekly_schedule (flujo real)
    if 'weekly_schedule' in pattern:
        weekly_schedule = pattern['weekly_schedule']
        day_index = {
            'sunday': 0,
            'monday': 1,
            'tuesday': 2,
            'wednesday': 3,
            'thursday': 4,
            'friday': 5,
            'saturday': 6,
        }
        
        with transaction.atomic():
            current_date = today
            while current_date <= horizon_end:
                day_of_week = current_date.weekday()  # 0=Monday, 6=Sunday
                # Convert to Sunday=0 format
                day_of_week_sunday = (day_of_week + 1) % 7
                
                # Find matching day name
                day_name = None
                for name, idx in day_index.items():
                    if idx == day_of_week_sunday:
                        day_name = name
                        break
                
                if day_name and day_name in weekly_schedule:
                    slots = weekly_schedule[day_name]
                    for slot in slots:
                        try:
                            # Parse start and end times
                            start_time_str = slot.get('startTime', '09:00')
                            end_time_str = slot.get('endTime')
                            
                            start_time = datetime.strptime(start_time_str, '%H:%M').time()
                            start_datetime = timezone.make_aware(
                                datetime.combine(current_date, start_time)
                            )
                            
                            # Calculate end datetime
                            if end_time_str:
                                end_time = datetime.strptime(end_time_str, '%H:%M').time()
                                end_datetime = timezone.make_aware(
                                    datetime.combine(current_date, end_time)
                                )
                            else:
                                # Use duration_minutes if end_time not provided
                                duration_minutes = experience.duration_minutes or 120
                                end_datetime = start_datetime + timedelta(minutes=duration_minutes)
                            
                            # Get languages (default to Spanish)
                            languages = slot.get('languages', ['es'])
                            if not isinstance(languages, list):
                                languages = ['es']
                            
                            # Get capacity
                            max_capacity = slot.get('capacity') or experience.max_participants
                            
                            # Create instance for each language
                            for lang in languages:
                                key = (start_datetime.isoformat(), lang)
                                if key in existing_keys:
                                    continue
                                
                                TourInstance.objects.create(
                                    experience=experience,
                                    start_datetime=start_datetime,
                                    end_datetime=end_datetime,
                                    language=lang,
                                    status='active',
                                    max_capacity=max_capacity,
                                    override_adult_price=slot.get('override_adult_price'),
                                    override_child_price=slot.get('override_child_price'),
                                    override_infant_price=slot.get('override_infant_price'),
                                )
                                
                                instances_created += 1
                                
                        except (ValueError, KeyError) as e:
                            logger.error(
                                f"🔴 [INSTANCE_GENERATION] Error processing slot in {day_name}: {e}"
                            )
                            continue
                
                # Move to next day
                current_date += timedelta(days=1)
    
    # Formato legacy (mantener compatibilidad)
    elif 'pattern' in pattern:
        times = pattern.get('times', [])
        days_of_week = pattern.get('days_of_week', [])
        start_date_str = pattern.get('start_date')
        end_date_str = pattern.get('end_date')
        
        if not start_date_str or not times or not days_of_week:
            logger.warning(
                f"⚠️ [INSTANCE_GENERATION] Experience {experience.id} has incomplete recurrence_pattern"
            )
            return 0
        
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        except ValueError:
            logger.error(
                f"🔴 [INSTANCE_GENERATION] Invalid start_date format: {start_date_str}"
            )
            return 0
        
        end_date = None
        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError:
                logger.error(
                    f"🔴 [INSTANCE_GENERATION] Invalid end_date format: {end_date_str}"
                )
        
        if end_date:
            actual_end_date = min(end_date, horizon_end)
        else:
            actual_end_date = horizon_end
        
        if start_date < today:
            start_date = today
        
        if start_date > actual_end_date:
            logger.info(
                f"ℹ️ [INSTANCE_GENERATION] Start date {start_date} is after end date {actual_end_date}"
            )
            return 0
        
        current_date = start_date
        
        with transaction.atomic():
            while current_date <= actual_end_date:
                day_of_week = current_date.weekday()
                day_of_week_sunday = (day_of_week + 1) % 7
                
                if day_of_week_sunday in days_of_week:
                    for time_str in times:
                        try:
                            time_obj = datetime.strptime(time_str, '%H:%M').time()
                            start_datetime = timezone.make_aware(
                                datetime.combine(current_date, time_obj)
                            )
                            duration_minutes = experience.duration_minutes or 120
                            end_datetime = start_datetime + timedelta(minutes=duration_minutes)
                            
                            key = (start_datetime.isoformat(), 'es')
                            if key in existing_keys:
                                continue
                            
                            TourInstance.objects.create(
                                experience=experience,
                                start_datetime=start_datetime,
                                end_datetime=end_datetime,
                                language='es',
                                status='active',
                                max_capacity=experience.max_participants
                            )
                            
                            instances_created += 1
                            
                        except ValueError as e:
                            logger.error(
                                f"🔴 [INSTANCE_GENERATION] Invalid time format '{time_str}': {e}"
                            )
                            continue
                
                current_date += timedelta(days=1)
    
    else:
        logger.warning(
            f"⚠️ [INSTANCE_GENERATION] Experience {experience.id} has unsupported recurrence_pattern format"
        )
        return 0
    
    logger.info(
        f"✅ [INSTANCE_GENERATION] Created {instances_created} instances for experience {experience.id}"
    )
    
    return instances_created

