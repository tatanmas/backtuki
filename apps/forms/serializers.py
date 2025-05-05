from rest_framework import serializers
from .models import Form, FormField, FieldOption, FieldValidation, ConditionalLogic

class FieldOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FieldOption
        fields = ['id', 'label', 'value', 'order']

class FieldValidationSerializer(serializers.ModelSerializer):
    class Meta:
        model = FieldValidation
        fields = ['id', 'type', 'value', 'message']

class ConditionalLogicSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConditionalLogic
        fields = ['id', 'source_field', 'condition', 'value']

class FormFieldSerializer(serializers.ModelSerializer):
    options = FieldOptionSerializer(many=True, required=False)
    validations = FieldValidationSerializer(many=True, required=False)
    conditional_logic = ConditionalLogicSerializer(many=True, required=False)
    
    class Meta:
        model = FormField
        fields = [
            'id', 'label', 'type', 'required', 'placeholder', 
            'help_text', 'default_value', 'order', 'width',
            'options', 'validations', 'conditional_logic'
        ]

class FormSerializer(serializers.ModelSerializer):
    fields = FormFieldSerializer(many=True, required=False)
    
    class Meta:
        model = Form
        fields = ['id', 'name', 'description', 'organizer', 'created_by', 
                 'created_at', 'updated_at', 'status', 'fields']
        read_only_fields = ['created_at', 'updated_at', 'created_by']
    
    def create(self, validated_data):
        fields_data = validated_data.pop('fields', [])
        form = Form.objects.create(**validated_data)
        
        for field_data in fields_data:
            options_data = field_data.pop('options', [])
            validations_data = field_data.pop('validations', [])
            conditional_logic_data = field_data.pop('conditional_logic', [])
            
            field = FormField.objects.create(form=form, **field_data)
            
            for option_data in options_data:
                FieldOption.objects.create(field=field, **option_data)
            
            for validation_data in validations_data:
                FieldValidation.objects.create(field=field, **validation_data)
            
            for logic_data in conditional_logic_data:
                source_field_id = logic_data.pop('source_field')
                source_field = FormField.objects.get(id=source_field_id)
                ConditionalLogic.objects.create(
                    field=field, 
                    source_field=source_field,
                    **logic_data
                )
        
        return form
    
    def update(self, instance, validated_data):
        fields_data = validated_data.pop('fields', [])
        
        # Update form fields
        instance.name = validated_data.get('name', instance.name)
        instance.description = validated_data.get('description', instance.description)
        instance.status = validated_data.get('status', instance.status)
        instance.save()
        
        # Handle fields update by clearing existing and creating new
        if fields_data:
            instance.fields.all().delete()  # Remove all existing fields
            
            for field_data in fields_data:
                options_data = field_data.pop('options', [])
                validations_data = field_data.pop('validations', [])
                conditional_logic_data = field_data.pop('conditional_logic', [])
                
                field = FormField.objects.create(form=instance, **field_data)
                
                for option_data in options_data:
                    FieldOption.objects.create(field=field, **option_data)
                
                for validation_data in validations_data:
                    FieldValidation.objects.create(field=field, **validation_data)
                
                for logic_data in conditional_logic_data:
                    source_field_id = logic_data.pop('source_field')
                    source_field = FormField.objects.get(id=source_field_id)
                    ConditionalLogic.objects.create(
                        field=field, 
                        source_field=source_field,
                        **logic_data
                    )
        
        return instance 