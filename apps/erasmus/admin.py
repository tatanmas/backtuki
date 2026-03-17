from django.contrib import admin
from .models import (
    ErasmusLead,
    ErasmusTrackingLink,
    ErasmusWhatsAppGroup,
    ErasmusPartnerNotificationConfig,
    ErasmusActivityNotificationConfig,
    ErasmusExtraField,
    ErasmusDestinationGuide,
    ErasmusLocalPartner,
    ErasmusMagicLink,
    ErasmusSlideConfig,
    ErasmusWelcomeMessageConfig,
    ErasmusRegistroBackgroundSlide,
    ErasmusTimelineItem,
    ErasmusActivity,
    ErasmusActivityExtraField,
    ErasmusActivityInstance,
    ErasmusActivityInstanceRegistration,
    ErasmusActivityPublicLink,
    ErasmusActivityReview,
    Contest,
    ContestSlideConfig,
    ContestExtraField,
    ContestRegistration,
    ContestParticipationCode,
)


@admin.register(ErasmusLead)
class ErasmusLeadAdmin(admin.ModelAdmin):
    list_display = ("first_name", "last_name", "stay_reason", "country", "city", "has_accommodation_in_chile", "wants_rumi4students_contact", "email", "phone_number", "university", "source_slug", "created_at")
    list_filter = ("stay_reason", "source_slug", "country", "has_accommodation_in_chile", "wants_rumi4students_contact", "created_at")
    search_fields = ("first_name", "last_name", "email", "instagram", "university", "stay_reason_detail", "country", "city")
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "created_at"


@admin.register(ErasmusDestinationGuide)
class ErasmusDestinationGuideAdmin(admin.ModelAdmin):
    list_display = ("title", "destination_slug", "order", "is_active", "file_url")
    list_filter = ("destination_slug", "is_active")
    search_fields = ("title", "destination_slug")
    ordering = ("destination_slug", "order")


@admin.register(ErasmusTrackingLink)
class ErasmusTrackingLinkAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name", "slug")


@admin.register(ErasmusWhatsAppGroup)
class ErasmusWhatsAppGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "link", "order", "is_active")
    list_filter = ("is_active",)
    list_editable = ("order", "is_active")
    search_fields = ("name",)
    ordering = ("order", "id")


@admin.register(ErasmusPartnerNotificationConfig)
class ErasmusPartnerNotificationConfigAdmin(admin.ModelAdmin):
    list_display = ("slug", "name", "whatsapp_chat", "is_active")
    list_filter = ("is_active",)
    search_fields = ("slug", "name")
    raw_id_fields = ("whatsapp_chat",)


@admin.register(ErasmusActivityNotificationConfig)
class ErasmusActivityNotificationConfigAdmin(admin.ModelAdmin):
    list_display = ("activity", "whatsapp_chat", "is_active")
    list_filter = ("is_active", "activity")
    raw_id_fields = ("activity", "whatsapp_chat")


@admin.register(ErasmusSlideConfig)
class ErasmusSlideConfigAdmin(admin.ModelAdmin):
    list_display = ['slide_id', 'asset', 'order']
    list_filter = ['slide_id']
    search_fields = ['slide_id']


@admin.register(ErasmusWelcomeMessageConfig)
class ErasmusWelcomeMessageConfigAdmin(admin.ModelAdmin):
    list_display = ('config_key', 'updated_at')
    readonly_fields = ('config_key', 'created_at', 'updated_at')
    # Editing is done from Super Admin panel (Erasmus > Mensajes de bienvenida)


@admin.register(ErasmusRegistroBackgroundSlide)
class ErasmusRegistroBackgroundSlideAdmin(admin.ModelAdmin):
    list_display = ['id', 'asset', 'order']
    list_editable = ['order']
    ordering = ['order', 'id']


@admin.register(ErasmusExtraField)
class ErasmusExtraFieldAdmin(admin.ModelAdmin):
    list_display = ("label", "field_key", "type", "required", "order", "is_active")
    list_filter = ("type", "is_active")
    search_fields = ("label", "field_key")
    ordering = ("order",)


@admin.register(ErasmusLocalPartner)
class ErasmusLocalPartnerAdmin(admin.ModelAdmin):
    list_display = ("name", "role", "instagram_username", "whatsapp_number", "order", "is_active")
    list_filter = ("is_active",)
    list_editable = ("order", "is_active")
    search_fields = ("name", "role", "instagram_username")
    ordering = ("order", "id")


@admin.register(ErasmusMagicLink)
class ErasmusMagicLinkAdmin(admin.ModelAdmin):
    list_display = ("lead", "target", "status", "verification_code", "expires_at", "used_at", "created_at")
    list_filter = ("target", "status")
    search_fields = ("lead__first_name", "lead__last_name", "verification_code", "access_token")
    readonly_fields = ("verification_code", "access_token", "created_at", "updated_at", "used_at")
    ordering = ("-created_at",)


@admin.register(ErasmusTimelineItem)
class ErasmusTimelineItemAdmin(admin.ModelAdmin):
    list_display = ("title_es", "scheduled_date", "location", "display_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("title_es", "title_en", "location")


class ErasmusActivityInstanceInline(admin.TabularInline):
    model = ErasmusActivityInstance
    extra = 0
    ordering = ("display_order", "scheduled_date", "scheduled_year", "scheduled_month")


class ErasmusActivityExtraFieldInline(admin.TabularInline):
    model = ErasmusActivityExtraField
    extra = 0
    ordering = ("order", "id")


@admin.register(ErasmusActivity)
class ErasmusActivityAdmin(admin.ModelAdmin):
    list_display = ("title_es", "slug", "location", "display_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("title_es", "title_en", "slug", "location")
    inlines = [ErasmusActivityInstanceInline, ErasmusActivityExtraFieldInline]


@admin.register(ErasmusActivityInstance)
class ErasmusActivityInstanceAdmin(admin.ModelAdmin):
    list_display = ("activity", "scheduled_date", "scheduled_month", "scheduled_year", "scheduled_label_es", "display_order", "is_active")
    list_filter = ("is_active", "activity")
    search_fields = ("scheduled_label_es", "scheduled_label_en")


@admin.register(ErasmusActivityExtraField)
class ErasmusActivityExtraFieldAdmin(admin.ModelAdmin):
    list_display = ("activity", "label", "field_key", "type", "required", "order", "is_active")
    list_filter = ("activity", "type", "is_active")
    search_fields = ("label", "field_key")
    ordering = ("activity", "order", "id")


@admin.register(ErasmusActivityInstanceRegistration)
class ErasmusActivityInstanceRegistrationAdmin(admin.ModelAdmin):
    list_display = ("lead", "instance", "created_at")
    list_filter = ("instance",)
    search_fields = ("lead__first_name", "lead__last_name")
    readonly_fields = ("created_at", "updated_at")
    raw_id_fields = ("lead", "instance")


@admin.register(ErasmusActivityPublicLink)
class ErasmusActivityPublicLinkAdmin(admin.ModelAdmin):
    list_display = ("activity", "view_token", "edit_token", "review_token", "links_enabled", "review_link_enabled")
    list_filter = ("links_enabled",)
    search_fields = ("activity__title_es", "view_token", "edit_token", "review_token")
    raw_id_fields = ("activity",)


@admin.register(ErasmusActivityReview)
class ErasmusActivityReviewAdmin(admin.ModelAdmin):
    list_display = ("id", "instance", "author_name", "author_origin", "rating", "created_at")
    list_filter = ("rating", "instance__activity")
    search_fields = ("author_name", "author_origin", "body")
    readonly_fields = ("created_at", "updated_at")
    raw_id_fields = ("instance", "lead")


# Contest / Sorteo
@admin.register(Contest)
class ContestAdmin(admin.ModelAdmin):
    list_display = ("slug", "title", "is_active", "starts_at", "ends_at", "order", "created_at")
    list_filter = ("is_active",)
    search_fields = ("slug", "title", "headline")
    prepopulated_fields = {"slug": ("title",)}
    raw_id_fields = ("experience",)


@admin.register(ContestSlideConfig)
class ContestSlideConfigAdmin(admin.ModelAdmin):
    list_display = ("contest", "order", "asset", "caption")
    list_filter = ("contest",)
    raw_id_fields = ("contest", "asset")


@admin.register(ContestExtraField)
class ContestExtraFieldAdmin(admin.ModelAdmin):
    list_display = ("contest", "label", "field_key", "type", "required", "order", "is_active")
    list_filter = ("contest", "type", "is_active")
    search_fields = ("label", "field_key")
    raw_id_fields = ("contest",)


@admin.register(ContestRegistration)
class ContestRegistrationAdmin(admin.ModelAdmin):
    list_display = ("contest", "first_name", "last_name", "email", "phone_number", "created_at")
    list_filter = ("contest",)
    search_fields = ("first_name", "last_name", "email", "phone_number")
    raw_id_fields = ("contest", "flow")
    readonly_fields = ("created_at", "updated_at")


@admin.register(ContestParticipationCode)
class ContestParticipationCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "contest", "registration", "status", "created_at")
    list_filter = ("contest", "status")
    search_fields = ("code",)
    raw_id_fields = ("contest", "registration", "flow")
