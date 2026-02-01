"""URLs for student centers API."""

from django.urls import path
from .views import (
    StudentCenterConfigView,
    StudentCenterExperiencesView,
    StudentCenterTimelineViewSet,
    StudentCenterUploadView,
    PublicStudentCenterView,
    PublicTimelineItemInterestsView,
)

urlpatterns = [
    # Configuration
    path('config/', StudentCenterConfigView.as_view(), name='student-center-config'),
    
    # Available experiences
    path('experiences/', StudentCenterExperiencesView.as_view(), name='student-center-experiences'),
    
    # Timeline
    path('timeline/', StudentCenterTimelineViewSet.as_view({'get': 'list', 'post': 'create'}), name='student-center-timeline'),
    path('timeline/<uuid:pk>/', StudentCenterTimelineViewSet.as_view({
        'get': 'retrieve',
        'put': 'update',
        'patch': 'partial_update',
        'delete': 'destroy'
    }), name='student-center-timeline-detail'),
    path('timeline/<uuid:pk>/confirm/', StudentCenterTimelineViewSet.as_view({'post': 'confirm'}), name='student-center-timeline-confirm'),
    path('timeline/<uuid:pk>/interests/', StudentCenterTimelineViewSet.as_view({'get': 'interests', 'post': 'interests'}), name='student-center-timeline-interests'),
    
    # Upload
    path('upload/', StudentCenterUploadView.as_view(), name='student-center-upload'),
    
    # Public endpoints (no authentication required)
    path('public/<str:slug>/', PublicStudentCenterView.as_view(), name='public-student-center'),
    path('public/timeline/<uuid:timeline_item_id>/interests/', PublicTimelineItemInterestsView.as_view(), name='public-timeline-item-interests'),
]

