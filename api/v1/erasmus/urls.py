from django.urls import path
from .views import (
    ErasmusOptionsView,
    ErasmusSlidesView,
    ErasmusTimelineView,
    ErasmusWhatsAppGroupsView,
    ErasmusTimelineEntryDetailView,
    ErasmusActivitiesListView,
    ErasmusActivityDetailView,
    ErasmusActivityDetailBySlugView,
    ErasmusActivityReviewsListView,
    ErasmusActivityInstanceDetailView,
    ErasmusRegisterView,
    ErasmusCommunityListView,
    ErasmusCommunityProfileUpdateView,
    ErasmusRequestWhatsAppApprovalView,
    ErasmusExpressInterestView,
    ErasmusMyActivitiesView,
    ErasmusMyGuidesView,
    ErasmusTrackVisitView,
    ErasmusTrackStepView,
    # Gracias page + magic-link flow
    ErasmusLocalPartnersView,
    ErasmusGenerateAccessCodeView,
    ErasmusMagicLoginView,
)
from .public_views import (
    ErasmusPublicViewInscritosView,
    ErasmusPublicViewMarkPaidView,
    ErasmusPublicViewGeneratePaymentLinkView,
    ErasmusPublicPaymentLinkByTokenView,
    ErasmusPublicEditActivityView,
    ErasmusPublicEditInstancesView,
    ErasmusPublicEditInstanceDetailView,
    ErasmusPublicEditInstanceInscriptionsView,
    ErasmusPublicReviewFormView,
)

urlpatterns = [
    # Content
    path("options/", ErasmusOptionsView.as_view(), name="erasmus-options"),
    path("whatsapp-groups/", ErasmusWhatsAppGroupsView.as_view(), name="erasmus-whatsapp-groups"),
    path("slides/", ErasmusSlidesView.as_view(), name="erasmus-slides"),
    path("timeline/", ErasmusTimelineView.as_view(), name="erasmus-timeline"),
    path("timeline/<uuid:entry_id>/", ErasmusTimelineEntryDetailView.as_view(), name="erasmus-timeline-entry-detail"),
    path("activities/", ErasmusActivitiesListView.as_view(), name="erasmus-activities-list"),
    path("activities/<uuid:activity_id>/", ErasmusActivityDetailView.as_view(), name="erasmus-activity-detail"),
    path("activities/<uuid:activity_id>/reviews/", ErasmusActivityReviewsListView.as_view(), name="erasmus-activity-reviews"),
    path("activities/by-slug/<str:slug>/", ErasmusActivityDetailBySlugView.as_view(), name="erasmus-activity-detail-by-slug"),
    path("instances/<uuid:instance_id>/", ErasmusActivityInstanceDetailView.as_view(), name="erasmus-instance-detail"),
    # Analytics
    path("track-visit/", ErasmusTrackVisitView.as_view(), name="erasmus-track-visit"),
    path("track-step/", ErasmusTrackStepView.as_view(), name="erasmus-track-step"),
    # Registration
    path("register/", ErasmusRegisterView.as_view(), name="erasmus-register"),
    # Community
    path("community/", ErasmusCommunityListView.as_view(), name="erasmus-community-list"),
    path("community-profile/", ErasmusCommunityProfileUpdateView.as_view(), name="erasmus-community-profile-update"),
    # Lead actions
    path("leads/<str:lead_id>/request-whatsapp-approval/", ErasmusRequestWhatsAppApprovalView.as_view(), name="erasmus-request-whatsapp-approval"),
    path("express-interest/", ErasmusExpressInterestView.as_view(), name="erasmus-express-interest"),
    path("my-activities/", ErasmusMyActivitiesView.as_view(), name="erasmus-my-activities"),
    path("my-guides/", ErasmusMyGuidesView.as_view(), name="erasmus-my-guides"),
    # Gracias page
    path("local-partners/", ErasmusLocalPartnersView.as_view(), name="erasmus-local-partners"),
    # Magic-link flow (2-phase WhatsApp)
    path("generate-access-code/", ErasmusGenerateAccessCodeView.as_view(), name="erasmus-generate-access-code"),
    path("magic-login/", ErasmusMagicLoginView.as_view(), name="erasmus-magic-login"),
    # Public links (no auth): view inscritos + full edit by token
    path("public/view/<str:view_token>/mark-paid/", ErasmusPublicViewMarkPaidView.as_view(), name="erasmus-public-view-mark-paid"),
    path("public/view/<str:view_token>/generate-payment-link/", ErasmusPublicViewGeneratePaymentLinkView.as_view(), name="erasmus-public-view-generate-payment-link"),
    path("public/view/<str:view_token>/", ErasmusPublicViewInscritosView.as_view(), name="erasmus-public-view-inscritos"),
    path("public/payment-link/<str:token>/", ErasmusPublicPaymentLinkByTokenView.as_view(), name="erasmus-public-payment-link-by-token"),
    path("public/edit/<str:edit_token>/", ErasmusPublicEditActivityView.as_view(), name="erasmus-public-edit-activity"),
    path("public/edit/<str:edit_token>/instances/", ErasmusPublicEditInstancesView.as_view(), name="erasmus-public-edit-instances"),
    path("public/edit/<str:edit_token>/instances/<uuid:instance_id>/", ErasmusPublicEditInstanceDetailView.as_view(), name="erasmus-public-edit-instance-detail"),
    path("public/edit/<str:edit_token>/instances/<uuid:instance_id>/inscriptions/", ErasmusPublicEditInstanceInscriptionsView.as_view(), name="erasmus-public-edit-instance-inscriptions"),
    path("public/review/<str:review_token>/", ErasmusPublicReviewFormView.as_view(), name="erasmus-public-review-form"),
]
