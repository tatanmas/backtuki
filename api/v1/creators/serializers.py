"""Serializers for TUKI Creators API."""

from rest_framework import serializers
from apps.creators.models import CreatorProfile, CreatorRecommendedExperience, Relato
from apps.experiences.models import Experience


class CreatorProfilePublicSerializer(serializers.ModelSerializer):
    """Public profile (by slug): no is_approved, no user."""
    recommended_experiences = serializers.SerializerMethodField()
    
    class Meta:
        model = CreatorProfile
        fields = [
            'id', 'slug', 'display_name', 'bio', 'avatar', 'location',
            'social_links', 'recommended_experiences', 'created_at', 'updated_at',
        ]
        read_only_fields = fields
    
    def get_recommended_experiences(self, obj):
        recs = obj.recommended_experiences.filter(
            experience__status='published',
            experience__is_active=True,
            experience__deleted_at__isnull=True,
        ).select_related('experience').order_by('order')
        return [ExperienceMinimalSerializer(r.experience).data for r in recs]


class ExperienceMinimalSerializer(serializers.ModelSerializer):
    """Minimal experience for creator profile and marketplace."""
    image_url = serializers.SerializerMethodField()
    
    class Meta:
        model = Experience
        fields = [
            'id', 'title', 'slug', 'short_description', 'price', 'currency',
            'image_url', 'location_name', 'duration_minutes',
        ]
    
    def get_image_url(self, obj):
        if obj.images and len(obj.images) > 0:
            return obj.images[0] if isinstance(obj.images[0], str) else obj.images[0].get('url')
        return None


class CreatorProfileMeSerializer(serializers.ModelSerializer):
    """Authenticated creator: full profile for GET/PATCH."""
    recommended_experiences = serializers.SerializerMethodField()
    
    class Meta:
        model = CreatorProfile
        fields = [
            'id', 'slug', 'display_name', 'bio', 'avatar', 'location', 'phone',
            'social_links', 'is_approved', 'bank_details', 'recommended_experiences',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'is_approved']
    
    def get_recommended_experiences(self, obj):
        recs = obj.recommended_experiences.select_related('experience').order_by('order')
        return [ExperienceMinimalSerializer(r.experience).data for r in recs]
    
    def validate_slug(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("El slug es requerido.")
        from django.utils.text import slugify
        s = slugify(value)
        if not s:
            raise serializers.ValidationError("El slug no es válido.")
        if CreatorProfile.objects.filter(slug=s).exclude(pk=self.instance.pk if self.instance else None).exists():
            raise serializers.ValidationError("Este slug ya está en uso.")
        return s  # return slugified value for storage


class CreatorApplySerializer(serializers.Serializer):
    """Apply as creator: creates CreatorProfile with is_approved=True (direct access, no approval queue)."""
    display_name = serializers.CharField(max_length=255)
    slug = serializers.CharField(max_length=100)
    bio = serializers.CharField(required=False, allow_blank=True, default='')
    phone = serializers.CharField(max_length=30, allow_blank=True)
    social_links = serializers.ListField(required=False, default=list)
    bank_details = serializers.JSONField(required=False, default=dict)

    def validate_slug(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("El handle (slug) es requerido.")
        from django.utils.text import slugify
        s = slugify(value)
        if not s:
            raise serializers.ValidationError("El handle no es válido.")
        if CreatorProfile.objects.filter(slug=s).exists():
            raise serializers.ValidationError("Este handle ya está en uso.")
        return s

    def create(self, validated_data):
        user = self.context['request'].user
        return CreatorProfile.objects.create(
            user=user,
            display_name=validated_data['display_name'].strip(),
            slug=validated_data['slug'],
            bio=validated_data.get('bio', '') or '',
            phone=validated_data.get('phone', '') or '',
            social_links=validated_data.get('social_links') or [],
            bank_details=validated_data.get('bank_details') or {},
            is_approved=True,
        )


def validate_body_blocks(value):
    """Validate relato body is a list of blocks; itinerary items have time, title, description."""
    if not isinstance(value, list):
        raise serializers.ValidationError("body debe ser una lista de bloques.")
    for i, block in enumerate(value):
        if not isinstance(block, dict):
            raise serializers.ValidationError(f"Bloque {i} debe ser un objeto.")
        block_type = block.get('type')
        if block_type == 'itinerary':
            items = block.get('items', [])
            if not isinstance(items, list):
                raise serializers.ValidationError(f"Bloque itinerario {i}: items debe ser una lista.")
            for j, item in enumerate(items):
                if not isinstance(item, dict):
                    raise serializers.ValidationError(f"Bloque itinerario {i}, item {j}: debe ser un objeto.")
                if not item.get('title'):
                    raise serializers.ValidationError(f"Bloque itinerario {i}, item {j}: title es requerido.")
                if not item.get('description'):
                    raise serializers.ValidationError(f"Bloque itinerario {i}, item {j}: description es requerido.")
    return value


class RelatoListSerializer(serializers.ModelSerializer):
    """List relatos (creator dashboard): id, title, slug, status, published_at, created_at."""
    class Meta:
        model = Relato
        fields = ['id', 'title', 'slug', 'status', 'published_at', 'created_at', 'updated_at']


class RelatoDetailSerializer(serializers.ModelSerializer):
    """Full relato for create/update (creator)."""
    class Meta:
        model = Relato
        fields = [
            'id', 'title', 'slug', 'body', 'status', 'published_at',
            'experience', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_body(self, value):
        return validate_body_blocks(value)

    def validate_slug(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("El slug es requerido.")
        from django.utils.text import slugify
        s = slugify(value)
        if not s:
            raise serializers.ValidationError("El slug no es válido.")
        creator = self.context.get('creator')
        if creator and Relato.objects.filter(creator=creator, slug=s).exclude(
            pk=self.instance.pk if self.instance else None
        ).exists():
            raise serializers.ValidationError("Ya tienes otro relato con este slug.")
        return s


class RelatoPublicSerializer(serializers.ModelSerializer):
    """Public relato (published only): no internal fields."""
    creator_slug = serializers.CharField(source='creator.slug', read_only=True)
    creator_display_name = serializers.CharField(source='creator.display_name', read_only=True)
    experience_title = serializers.SerializerMethodField()

    class Meta:
        model = Relato
        fields = [
            'id', 'title', 'slug', 'body', 'published_at',
            'creator_slug', 'creator_display_name', 'experience_title',
            'created_at', 'updated_at',
        ]

    def get_experience_title(self, obj):
        return (obj.experience.title if obj.experience else None)
