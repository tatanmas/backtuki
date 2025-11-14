"""
Serializers for Satisfaction Survey System
"""

from rest_framework import serializers
from .models import (
    SatisfactionSurvey,
    SatisfactionQuestion,
    SatisfactionQuestionOption,
    SatisfactionResponse,
    SatisfactionAnswer
)


class SatisfactionQuestionOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SatisfactionQuestionOption
        fields = ['id', 'option_text', 'order']


class SatisfactionQuestionSerializer(serializers.ModelSerializer):
    options = SatisfactionQuestionOptionSerializer(many=True, read_only=True)
    
    class Meta:
        model = SatisfactionQuestion
        fields = [
            'id', 'question_text', 'question_type', 'required',
            'order', 'help_text', 'min_rating', 'max_rating', 'options'
        ]


class SatisfactionQuestionWriteSerializer(serializers.ModelSerializer):
    """Serializer para escribir preguntas con opciones."""
    options = SatisfactionQuestionOptionSerializer(many=True, required=False, allow_empty=True)
    
    class Meta:
        model = SatisfactionQuestion
        fields = [
            'question_text', 'question_type', 'required',
            'order', 'help_text', 'min_rating', 'max_rating', 'options'
        ]


class SatisfactionSurveySerializer(serializers.ModelSerializer):
    questions = SatisfactionQuestionSerializer(many=True, read_only=True)
    questions_data = SatisfactionQuestionWriteSerializer(many=True, write_only=True, required=False)
    total_responses = serializers.IntegerField(read_only=True)
    completion_rate = serializers.FloatField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = SatisfactionSurvey
        fields = [
            'id', 'title', 'description', 'slug', 'status',
            'event', 'organizer', 'is_template',
            'opens_at', 'closes_at',
            'allow_multiple_responses', 'require_email',
            'questions', 'questions_data', 'total_responses', 'completion_rate', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def create(self, validated_data):
        questions_data = validated_data.pop('questions_data', [])
        survey = SatisfactionSurvey.objects.create(**validated_data)
        
        # Crear las preguntas
        for question_data in questions_data:
            options_data = question_data.pop('options', [])
            question = SatisfactionQuestion.objects.create(
                survey=survey,
                **question_data
            )
            
            # Crear las opciones si existen
            for option_data in options_data:
                SatisfactionQuestionOption.objects.create(
                    question=question,
                    **option_data
                )
        
        return survey
    
    def update(self, instance, validated_data):
        questions_data = validated_data.pop('questions_data', None)
        
        # Actualizar campos del survey
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Si se proporcionan preguntas, reemplazarlas
        if questions_data is not None:
            # Eliminar preguntas existentes
            instance.questions.all().delete()
            
            # Crear nuevas preguntas
            for question_data in questions_data:
                options_data = question_data.pop('options', [])
                question = SatisfactionQuestion.objects.create(
                    survey=instance,
                    **question_data
                )
                
                # Crear las opciones si existen
                for option_data in options_data:
                    SatisfactionQuestionOption.objects.create(
                        question=question,
                        **option_data
                    )
        
        return instance


class SatisfactionSurveyListSerializer(serializers.ModelSerializer):
    """Serializer simplificado para listado."""
    total_responses = serializers.IntegerField(read_only=True)
    event_title = serializers.CharField(source='event.title', read_only=True)
    organizer_name = serializers.CharField(source='organizer.name', read_only=True)
    
    class Meta:
        model = SatisfactionSurvey
        fields = [
            'id', 'title', 'slug', 'status', 'event_title',
            'organizer_name', 'total_responses', 'created_at'
        ]


class SatisfactionAnswerSerializer(serializers.ModelSerializer):
    question_text = serializers.CharField(source='question.question_text', read_only=True)
    question_type = serializers.CharField(source='question.question_type', read_only=True)
    
    class Meta:
        model = SatisfactionAnswer
        fields = [
            'id', 'question', 'question_text', 'question_type',
            'numeric_value', 'text_value', 'option'
        ]


class SatisfactionResponseSerializer(serializers.ModelSerializer):
    answers = SatisfactionAnswerSerializer(many=True, read_only=True)
    survey_title = serializers.CharField(source='survey.title', read_only=True)
    
    class Meta:
        model = SatisfactionResponse
        fields = [
            'id', 'survey', 'survey_title', 'email', 'name',
            'ticket', 'answers', 'submitted_at'
        ]
        read_only_fields = ['id', 'submitted_at']


class SatisfactionResponseCreateSerializer(serializers.ModelSerializer):
    """Serializer para crear respuestas desde la página pública."""
    answers = serializers.ListField(
        child=serializers.DictField(),
        write_only=True
    )
    email = serializers.EmailField(required=False, allow_null=True, allow_blank=True)
    name = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=255)
    
    class Meta:
        model = SatisfactionResponse
        fields = ['survey', 'email', 'name', 'answers']
    
    def create(self, validated_data):
        answers_data = validated_data.pop('answers', [])
        survey = validated_data['survey']
        
        # Validar que el formulario esté activo
        if not survey.is_active:
            raise serializers.ValidationError("Este formulario no está disponible actualmente.")
        
        # Crear la respuesta
        response = SatisfactionResponse.objects.create(**validated_data)
        
        # Crear las respuestas individuales
        for answer_data in answers_data:
            question_id = answer_data.get('question_id')
            try:
                question = SatisfactionQuestion.objects.get(id=question_id, survey=survey)
            except SatisfactionQuestion.DoesNotExist:
                continue
            
            # Validar respuesta requerida
            if question.required and not any([
                answer_data.get('numeric_value'),
                answer_data.get('text_value'),
                answer_data.get('option_id')
            ]):
                raise serializers.ValidationError(
                    f"La pregunta '{question.question_text}' es requerida."
                )
            
            SatisfactionAnswer.objects.create(
                response=response,
                question=question,
                numeric_value=answer_data.get('numeric_value'),
                text_value=answer_data.get('text_value'),
                option_id=answer_data.get('option_id')
            )
        
        return response


class SatisfactionStatisticsSerializer(serializers.Serializer):
    """Serializer para estadísticas del formulario."""
    total_responses = serializers.IntegerField()
    completion_rate = serializers.FloatField(allow_null=True)
    average_ratings = serializers.DictField()
    question_statistics = serializers.ListField()

