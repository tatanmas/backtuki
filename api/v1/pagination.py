"""Shared pagination classes for API v1."""

from rest_framework.pagination import PageNumberPagination


class LargePageSizePagination(PageNumberPagination):
    """
    Pagination that allows client to request large page sizes (e.g. for admin pickers
    that need to load all experiences, events, etc.).
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 5000
    page_query_param = 'page'
