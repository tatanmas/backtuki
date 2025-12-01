from rest_framework import serializers
from .models import Form, FormField, FieldOption, FieldValidation, ConditionalLogic, FormResponse, FormResponseFile

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
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'organizer']
    
    def to_representation(self, instance):
        """Override to ensure fields are ordered by 'order' field."""
        print(f"[FormSerializer.to_representation] Serializing form: {instance.id} - {instance.name}")
        print(f"[FormSerializer.to_representation] Form has {instance.fields.count()} fields")
        
        representation = super().to_representation(instance)
        print(f"[FormSerializer.to_representation] Base representation keys: {representation.keys()}")
        print(f"[FormSerializer.to_representation] Fields in representation: {representation.get('fields')}")
        
        # Order fields by the 'order' field
        if 'fields' in representation and isinstance(representation['fields'], list):
            print(f"[FormSerializer.to_representation] Ordering {len(representation['fields'])} fields")
            representation['fields'] = sorted(
                representation['fields'],
                key=lambda x: x.get('order', 0)
            )
            print(f"[FormSerializer.to_representation] Ordered fields: {[f.get('label', 'no-label') for f in representation['fields']]}")
        else:
            print(f"[FormSerializer.to_representation] WARNING: fields is not a list or doesn't exist")
            print(f"[FormSerializer.to_representation] Fields type: {type(representation.get('fields'))}")
            print(f"[FormSerializer.to_representation] Fields value: {representation.get('fields')}")
        
        return representation
    
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
        """Update form and handle nested fields."""
        print(f"[FormSerializer.update] Updating form: {instance.id} - {instance.name}")
        fields_data = validated_data.pop('fields', None)
        
        # Update basic form fields
        instance.name = validated_data.get('name', instance.name)
        instance.description = validated_data.get('description', instance.description)
        instance.status = validated_data.get('status', instance.status)
        instance.save()
        
        print(f"[FormSerializer.update] Fields data provided: {fields_data is not None}")
        
        # Handle fields update
        if fields_data is not None:
            print(f"[FormSerializer.update] Processing {len(fields_data)} fields")
            
            # Get existing field IDs to track which ones to keep
            existing_field_ids = set(instance.fields.values_list('id', flat=True))
            incoming_field_ids = {field_data.get('id') for field_data in fields_data if field_data.get('id')}
            
            # Delete fields that are not in the incoming data
            fields_to_delete = existing_field_ids - incoming_field_ids
            if fields_to_delete:
                print(f"[FormSerializer.update] Deleting {len(fields_to_delete)} fields: {fields_to_delete}")
                FormField.objects.filter(id__in=fields_to_delete).delete()
            
            # Update or create fields
            for field_data in fields_data:
                field_id = field_data.pop('id', None)
                options_data = field_data.pop('options', [])
                validations_data = field_data.pop('validations', [])
                conditional_logic_data = field_data.pop('conditional_logic', [])
                
                if field_id and field_id in existing_field_ids:
                    # Update existing field
                    print(f"[FormSerializer.update] Updating field ID: {field_id}")
                    field = FormField.objects.get(id=field_id, form=instance)
                    for attr, value in field_data.items():
                        setattr(field, attr, value)
                    field.save()
                    
                    # Delete existing related objects
                    field.options.all().delete()
                    field.validations.all().delete()
                    field.conditional_logic.all().delete()
                else:
                    # Create new field
                    print(f"[FormSerializer.update] Creating new field")
                    field = FormField.objects.create(form=instance, **field_data)
                
                # Create options
                for option_data in options_data:
                    FieldOption.objects.create(field=field, **option_data)
                
                # Create validations
                for validation_data in validations_data:
                    FieldValidation.objects.create(field=field, **validation_data)
                
                # Create conditional logic
                for logic_data in conditional_logic_data:
                    source_field_id = logic_data.pop('source_field', None)
                    if source_field_id:
                        try:
                            source_field = FormField.objects.get(id=source_field_id, form=instance)
                            ConditionalLogic.objects.create(
                                field=field,
                                source_field=source_field,
                                **logic_data
                            )
                        except FormField.DoesNotExist:
                            print(f"[FormSerializer.update] WARNING: Source field {source_field_id} not found")
        
        print(f"[FormSerializer.update] Update completed")
        return instance


# 🚀 ENTERPRISE: Form Response Serializers
class FormResponseFileSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField()
    file_size_mb = serializers.ReadOnlyField()
    
    class Meta:
        model = FormResponseFile
        fields = [
            'id', 'field', 'original_filename', 'file_size', 'file_size_mb',
            'content_type', 'uploaded_at', 'download_url'
        ]
    
    def get_download_url(self, obj):
        return obj.get_download_url()


class FormResponseSerializer(serializers.ModelSerializer):
    files = FormResponseFileSerializer(many=True, read_only=True)
    ticket_info = serializers.SerializerMethodField()
    
    class Meta:
        model = FormResponse
        fields = [
            'id', 'form', 'ticket', 'submitted_at', 'updated_at',
            'response_data', 'files', 'ticket_info'
        ]
        read_only_fields = ['submitted_at', 'updated_at']
    
    def get_ticket_info(self, obj):
        if obj.ticket:
            return {
                'ticket_number': obj.ticket.ticket_number,
                'attendee_name': f"{obj.ticket.first_name} {obj.ticket.last_name}",
                'email': obj.ticket.email
            }
        return None
    
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