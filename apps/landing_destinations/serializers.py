"""Serializers for landing destinations."""

from rest_framework import serializers
from .models import LandingDestination, LandingDestinationExperience, LandingDestinationEvent


class LandingDestinationSerializer(serializers.ModelSerializer):
    """Full serializer for superadmin CRUD."""

    experience_ids = serializers.SerializerMethodField()
    event_ids = serializers.SerializerMethodField()

    class Meta:
        model = LandingDestination
        fields = [
            "id",
            "name",
            "slug",
            "country",
            "region",
            "description",
            "hero_image",
            "hero_media_id",
            "gallery_media_ids",
            "latitude",
            "longitude",
            "temperature",
            "local_time",
            "is_active",
            "images",
            "travel_guides",
            "transportation",
            "accommodation_ids",
            "experience_ids",
            "event_ids",
            "featured_type",
            "featured_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_experience_ids(self, obj):
        return [str(e.experience_id) for e in obj.destination_experiences.order_by("order")]

    def get_event_ids(self, obj):
        return [str(e.event_id) for e in obj.destination_events.order_by("order")]

    def to_internal_value(self, data):
        ret = super().to_internal_value(data)
        if "experience_ids" in data:
            ret["experience_ids"] = data["experience_ids"]
        if "event_ids" in data:
            ret["event_ids"] = data["event_ids"]
        return ret

    def _update_relation_ids(self, instance, relation_name, model_class, id_attr, ids):
        if ids is None:
            return
        model_class.objects.filter(destination=instance).delete()
        for i, eid in enumerate(ids):
            try:
                uuid_val = str(eid).strip()
                if uuid_val:
                    model_class.objects.create(
                        destination=instance,
                        **{id_attr: uuid_val},
                        order=i,
                    )
            except Exception:
                pass

    def create(self, validated_data):
        experience_ids = validated_data.pop("experience_ids", None) or self.initial_data.get("experience_ids")
        event_ids = validated_data.pop("event_ids", None) or self.initial_data.get("event_ids")
        instance = super().create(validated_data)
        self._update_relation_ids(
            instance, "destination_experiences", LandingDestinationExperience, "experience_id", experience_ids
        )
        self._update_relation_ids(
            instance, "destination_events", LandingDestinationEvent, "event_id", event_ids
        )
        return instance

    def update(self, instance, validated_data):
        experience_ids = validated_data.pop("experience_ids", None) or self.initial_data.get("experience_ids")
        event_ids = validated_data.pop("event_ids", None) or self.initial_data.get("event_ids")
        instance = super().update(instance, validated_data)
        self._update_relation_ids(
            instance, "destination_experiences", LandingDestinationExperience, "experience_id", experience_ids
        )
        self._update_relation_ids(
            instance, "destination_events", LandingDestinationEvent, "event_id", event_ids
        )
        return instance


class LandingDestinationListSerializer(serializers.ModelSerializer):
    """Minimal serializer for list/search."""

    class Meta:
        model = LandingDestination
        fields = ["id", "name", "slug", "country", "region", "hero_image", "hero_media_id", "is_active"]
