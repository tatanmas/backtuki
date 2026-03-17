from django.urls import path
from .views import ContestDetailView, ContestTermsView, ContestRegisterView

urlpatterns = [
    path("<str:slug>/", ContestDetailView.as_view(), name="contest-detail"),
    path("<str:slug>/terms/", ContestTermsView.as_view(), name="contest-terms"),
    path("<str:slug>/register/", ContestRegisterView.as_view(), name="contest-register"),
]
