"""
Custom throttle classes for the Tuki API.
"""

from rest_framework.throttling import SimpleRateThrottle


class LoginRateThrottle(SimpleRateThrottle):
    """
    Strict rate limit for JWT login (POST /api/v1/auth/token/).
    Uses scope 'login' (e.g. 10/min per IP) to mitigate brute force.
    """
    scope = 'login'

    def get_cache_key(self, request, view):
        # Throttle by IP for all login attempts
        return self.cache_format % {
            'scope': self.scope,
            'ident': self.get_ident(request),
        }
