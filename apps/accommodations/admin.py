"""Admin for accommodations."""

from django.contrib import admin
from .models import (
    Accommodation,
    AccommodationBlockedDate,
    AccommodationReservation,
    AccommodationReview,
    RentalHub,
)


class AccommodationReviewInline(admin.TabularInline):
    model = AccommodationReview
    extra = 0
    fields = ("author_name", "author_location", "rating", "review_date", "text", "host_reply")


class AccommodationBlockedDateInline(admin.TabularInline):
    model = AccommodationBlockedDate
    extra = 0
    fields = ("date",)


@admin.register(Accommodation)
class AccommodationAdmin(admin.ModelAdmin):
    list_display = (
        "title", "slug", "rental_hub", "unit_type", "tower", "unit_number",
        "city", "country", "status", "guests", "bedrooms", "price", "rating_avg", "review_count",
    )
    list_filter = ("status", "property_type", "country", "rental_hub", "unit_type", "tower")
    search_fields = ("title", "slug", "city", "location_name", "unit_number")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [AccommodationReviewInline, AccommodationBlockedDateInline]


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


@admin.register(RentalHub)
class RentalHubAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(AccommodationBlockedDate)
class AccommodationBlockedDateAdmin(admin.ModelAdmin):
    list_display = ("accommodation", "date")
    list_filter = ("date",)
    search_fields = ("accommodation__title",)
    raw_id_fields = ("accommodation",)
