"""
Enterprise Satisfaction Survey System
Sistema robusto para formularios de satisfacción de eventos.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from core.models import TimeStampedModel, UUIDModel
from apps.events.models import Event
from apps.organizers.models import Organizer
from apps.users.models import User


class SatisfactionSurvey(TimeStampedModel, UUIDModel):
    """
    Modelo principal para formularios de satisfacción.
    Puede estar vinculado a un evento específico o ser genérico.
    """
    
    STATUS_CHOICES = (
        ('draft', _('Draft')),
        ('active', _('Active')),
        ('closed', _('Closed')),
    )
    
    title = models.CharField(_("title"), max_length=255)
    description = models.TextField(_("description"), blank=True, null=True)
    slug = models.SlugField(_("slug"), unique=True, help_text=_("URL-friendly identifier"))
    
    # Vinculación opcional a evento y organizador
    event = models.ForeignKey(
        Event,
        on_delete=models.SET_NULL,
        related_name='satisfaction_surveys',
        null=True,
        blank=True,
        verbose_name=_("event")
    )
    organizer = models.ForeignKey(
        Organizer,
        on_delete=models.SET_NULL,
        related_name='satisfaction_surveys',
        null=True,
        blank=True,
        verbose_name=_("organizer")
    )
    
    # Configuración
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft'
    )
    is_template = models.BooleanField(
        _("is template"),
        default=False,
        help_text=_("Si es una plantilla reutilizable")
    )
    
    # Fechas
    opens_at = models.DateTimeField(
        _("opens at"),
        null=True,
        blank=True,
        help_text=_("Fecha de apertura del formulario")
    )
    closes_at = models.DateTimeField(
        _("closes at"),
        null=True,
        blank=True,
        help_text=_("Fecha de cierre del formulario")
    )
    
    # Configuración de respuestas
    allow_multiple_responses = models.BooleanField(
        _("allow multiple responses"),
        default=False,
        help_text=_("Permitir múltiples respuestas del mismo usuario")
    )
    require_email = models.BooleanField(
        _("require email"),
        default=False,
        help_text=_("Requerir email para responder")
    )
    
    # Metadata
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_satisfaction_surveys',
        verbose_name=_("created by")
    )
    
    class Meta:
        verbose_name = _("satisfaction survey")
        verbose_name_plural = _("satisfaction surveys")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['status']),
            models.Index(fields=['event']),
        ]
    
    def __str__(self):
        return self.title
    
    @property
    def is_active(self):
        """Verificar si el formulario está activo."""
        if self.status != 'active':
            return False
        now = timezone.now()
        if self.opens_at and now < self.opens_at:
            return False
        if self.closes_at and now > self.closes_at:
            return False
        return True
    
    @property
    def total_responses(self):
        """Total de respuestas recibidas."""
        return self.responses.count()
    
    @property
    def completion_rate(self):
        """Tasa de completitud (si hay evento vinculado)."""
        if not self.event:
            return None
        total_tickets = self.event.tickets.filter(status='paid').count()
        if total_tickets == 0:
            return 0
        return round((self.total_responses / total_tickets) * 100, 2)


class SatisfactionQuestion(TimeStampedModel):
    """
    Preguntas del formulario de satisfacción.
    """
    
    QUESTION_TYPE_CHOICES = (
        ('rating', _('Rating (Stars)')),
        ('rating_10', _('Rating (1-10)')),
        ('rating_5', _('Rating (1-5)')),
        ('text', _('Text (Free)')),
        ('textarea', _('Long Text')),
        ('multiple_choice', _('Multiple Choice')),
        ('yes_no', _('Yes/No')),
    )
    
    survey = models.ForeignKey(
        SatisfactionSurvey,
        on_delete=models.CASCADE,
        related_name='questions',
        verbose_name=_("survey")
    )
    question_text = models.CharField(_("question text"), max_length=500)
    question_type = models.CharField(
        _("question type"),
        max_length=20,
        choices=QUESTION_TYPE_CHOICES
    )
    required = models.BooleanField(_("required"), default=True)
    order = models.PositiveIntegerField(_("order"), default=0)
    help_text = models.TextField(_("help text"), blank=True)
    
    # Configuración específica por tipo
    min_rating = models.IntegerField(
        _("min rating"),
        default=1,
        help_text=_("Valor mínimo para ratings")
    )
    max_rating = models.IntegerField(
        _("max rating"),
        default=5,
        help_text=_("Valor máximo para ratings")
    )
    
    class Meta:
        verbose_name = _("satisfaction question")
        verbose_name_plural = _("satisfaction questions")
        ordering = ['order', 'created_at']
    
    def __str__(self):
        return f"{self.survey.title} - {self.question_text[:50]}"


class SatisfactionQuestionOption(models.Model):
    """
    Opciones para preguntas de selección múltiple.
    """
    question = models.ForeignKey(
        SatisfactionQuestion,
        on_delete=models.CASCADE,
        related_name='options',
        verbose_name=_("question")
    )
    option_text = models.CharField(_("option text"), max_length=255)
    order = models.PositiveIntegerField(_("order"), default=0)
    
    class Meta:
        ordering = ['order']
    
    def __str__(self):
        return self.option_text


class SatisfactionResponse(TimeStampedModel, UUIDModel):
    """
    Respuesta completa de un usuario al formulario de satisfacción.
    """
    survey = models.ForeignKey(
        SatisfactionSurvey,
        on_delete=models.CASCADE,
        related_name='responses',
        verbose_name=_("survey")
    )
    
    # Información del respondente (opcional)
    email = models.EmailField(_("email"), blank=True, null=True)
    name = models.CharField(_("name"), max_length=255, blank=True, null=True)
    
    # Metadata
    ip_address = models.GenericIPAddressField(_("IP address"), null=True, blank=True)
    user_agent = models.TextField(_("user agent"), blank=True)
    submitted_at = models.DateTimeField(_("submitted at"), auto_now_add=True)
    
    # Vinculación opcional a ticket/orden
    ticket = models.ForeignKey(
        'events.Ticket',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='satisfaction_responses',
        verbose_name=_("ticket")
    )
    
    class Meta:
        verbose_name = _("satisfaction response")
        verbose_name_plural = _("satisfaction responses")
        ordering = ['-submitted_at']
        indexes = [
            models.Index(fields=['survey', '-submitted_at']),
            models.Index(fields=['email']),
        ]
    
    def __str__(self):
        identifier = self.email or self.name or f"Response {self.id}"
        return f"{self.survey.title} - {identifier}"


class SatisfactionAnswer(models.Model):
    """
    Respuesta individual a una pregunta específica.
    """
    response = models.ForeignKey(
        SatisfactionResponse,
        on_delete=models.CASCADE,
        related_name='answers',
        verbose_name=_("response")
    )
    question = models.ForeignKey(
        SatisfactionQuestion,
        on_delete=models.CASCADE,
        related_name='answers',
        verbose_name=_("question")
    )
    
    # Respuesta puede ser numérica (rating) o texto
    numeric_value = models.IntegerField(_("numeric value"), null=True, blank=True)
    text_value = models.TextField(_("text value"), null=True, blank=True)
    option = models.ForeignKey(
        SatisfactionQuestionOption,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("selected option")
    )
    
    class Meta:
        verbose_name = _("satisfaction answer")
        verbose_name_plural = _("satisfaction answers")
        unique_together = [['response', 'question']]
    
    def __str__(self):
        value = self.numeric_value or self.text_value or (self.option.option_text if self.option else "N/A")
        return f"{self.question.question_text}: {value}"

