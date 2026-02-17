"""Admin for accommodations."""

from django.contrib import admin
from .models import Accommodation, AccommodationReview, AccommodationReservation


class AccommodationReviewInline(admin.TabularInline):
    model = AccommodationReview
    extra = 0
    fields = ("author_name", "author_location", "rating", "review_date", "text", "host_reply")


@admin.register(Accommodation)
class AccommodationAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "city", "country", "status", "guests", "bedrooms", "price", "rating_avg", "review_count")
    list_filter = ("status", "property_type", "country")
    search_fields = ("title", "slug", "city", "location_name")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [AccommodationReviewInline]


@admin.register(AccommodationReview)
class AccommodationReviewAdmin(admin.ModelAdmin):
    list_display = ("author_name", "accommodation", "rating", "review_date", "created_at")
    list_filter = ("rating",)
    search_fields = ("author_name", "text")


@admin.register(AccommodationReservation)
class AccommodationReservationAdmin(admin.ModelAdmin):
    list_display = ("reservation_id", "accommodation", "check_in", "check_out", "guests", "status", "total", "created_at")
    list_filter = ("status",)
    search_fields = ("reservation_id", "first_name", "last_name", "email")
    raw_id_fields = ("accommodation", "user")
