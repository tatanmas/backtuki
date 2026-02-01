"""Custom pagination classes for terminal app."""

from rest_framework.pagination import PageNumberPagination


class TerminalTripPagination(PageNumberPagination):
    """Pagination class for TerminalTrip that allows custom page size."""
    
    page_size = 20  # Default page size
    page_size_query_param = 'page_size'  # Allow client to override page size via query param
    max_page_size = 1000  # Maximum page size allowed (to prevent abuse)
    page_query_param = 'page'  # Standard page parameter

