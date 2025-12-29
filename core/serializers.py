"""Serializers for core models."""

from rest_framework import serializers
from core.models import Country


class CountrySerializer(serializers.ModelSerializer):
    """Serializer for Country model."""
    
    class Meta:
        model = Country
        fields = ['id', 'name', 'code', 'is_active', 'display_order', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

