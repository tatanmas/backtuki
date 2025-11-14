from django.contrib import admin
from .models import (
    SatisfactionSurvey,
    SatisfactionQuestion,
    SatisfactionQuestionOption,
    SatisfactionResponse,
    SatisfactionAnswer
)


@admin.register(SatisfactionSurvey)
class SatisfactionSurveyAdmin(admin.ModelAdmin):
    list_display = ['title', 'status', 'event', 'organizer', 'total_responses', 'created_at']
    list_filter = ['status', 'is_template', 'created_at']
    search_fields = ['title', 'slug', 'description']
    readonly_fields = ['id', 'created_at', 'updated_at']
    fieldsets = (
        ('Información básica', {
            'fields': ('title', 'slug', 'description', 'status', 'is_template')
        }),
        ('Vinculación', {
            'fields': ('event', 'organizer')
        }),
        ('Configuración', {
            'fields': (
                'opens_at', 'closes_at',
                'allow_multiple_responses', 'require_email'
            )
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at', 'updated_at', 'id')
        }),
    )


class SatisfactionQuestionOptionInline(admin.TabularInline):
    model = SatisfactionQuestionOption
    extra = 1


@admin.register(SatisfactionQuestion)
class SatisfactionQuestionAdmin(admin.ModelAdmin):
    list_display = ['question_text', 'survey', 'question_type', 'required', 'order']
    list_filter = ['question_type', 'required', 'survey']
    search_fields = ['question_text']
    inlines = [SatisfactionQuestionOptionInline]
    ordering = ['survey', 'order']


@admin.register(SatisfactionResponse)
class SatisfactionResponseAdmin(admin.ModelAdmin):
    list_display = ['survey', 'email', 'name', 'submitted_at', 'ticket']
    list_filter = ['survey', 'submitted_at']
    search_fields = ['email', 'name']
    readonly_fields = ['id', 'submitted_at', 'created_at', 'updated_at']
    date_hierarchy = 'submitted_at'


@admin.register(SatisfactionAnswer)
class SatisfactionAnswerAdmin(admin.ModelAdmin):
    list_display = ['response', 'question', 'numeric_value', 'text_value']
    list_filter = ['question', 'question__question_type']
    search_fields = ['text_value']

