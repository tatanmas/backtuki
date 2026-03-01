"""Admin for car rental."""

from django.contrib import admin
from .models import CarRentalCompany, Car, CarBlockedDate, CarReservation


class CarInline(admin.TabularInline):
    model = Car
    extra = 0
    fields = ("title", "slug", "status", "price_per_day", "currency")
    show_change_link = True


class CarBlockedDateInline(admin.TabularInline):
    model = CarBlockedDate
    extra = 0
    fields = ("date",)


@admin.register(CarRentalCompany)
class CarRentalCompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "country", "city", "created_at")
    list_filter = ("is_active", "country")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [CarInline]


@admin.register(Car)
class CarAdmin(admin.ModelAdmin):
    list_display = (
        "title", "slug", "company", "status", "price_per_day", "currency",
        "transmission", "seats", "created_at",
    )
    list_filter = ("status", "company", "transmission")
    search_fields = ("title", "slug")
    prepopulated_fields = {"slug": ("title",)}
    raw_id_fields = ("company",)
    inlines = [CarBlockedDateInline]


@admin.register(CarBlockedDate)
class CarBlockedDateAdmin(admin.ModelAdmin):
    list_display = ("car", "date")
    list_filter = ("date",)
    search_fields = ("car__title",)
    raw_id_fields = ("car",)


@admin.register(CarReservation)
class CarReservationAdmin(admin.ModelAdmin):
    list_display = (
        "reservation_id", "car", "pickup_date", "return_date",
        "pickup_time", "return_time", "status", "total", "created_at",
    )
    list_filter = ("status",)
    search_fields = ("reservation_id", "first_name", "last_name", "email")
    raw_id_fields = ("car", "user")
