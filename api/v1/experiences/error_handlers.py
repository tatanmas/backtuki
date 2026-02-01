"""
🚀 ENTERPRISE: Centralized Error Handling for Experiences API

This module provides robust, enterprise-level error handling utilities
for the experiences API endpoints. All error responses are structured,
consistent, and provide actionable information to clients.
"""

import logging
from typing import Dict, Any, Optional, List
from rest_framework import status
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError, PermissionDenied, AuthenticationFailed
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, DatabaseError

logger = logging.getLogger(__name__)


class ExperienceErrorHandler:
    """
    🚀 ENTERPRISE: Centralized error handler for experience operations.
    
    Provides consistent error formatting, logging, and response generation
    across all experience-related endpoints.
    """
    
    @staticmethod
    def handle_validation_error(
        error: ValidationError,
        context: Optional[Dict[str, Any]] = None
    ) -> Response:
        """
        Handle DRF ValidationError with structured field-level error messages.
        
        Args:
            error: The ValidationError exception
            context: Additional context for logging
            
        Returns:
            Response with structured error details
        """
        error_context = context or {}
        logger.warning(
            f"🔴 [EXPERIENCE_ERROR] Validation error: {error.detail}",
            extra={
                'error_type': 'validation',
                'error_detail': str(error.detail),
                **error_context
            }
        )
        
        # Extract field-level errors
        if isinstance(error.detail, dict):
            field_errors = {}
            general_errors = []
            
            for field, messages in error.detail.items():
                if isinstance(messages, list):
                    field_errors[field] = [str(msg) for msg in messages]
                else:
                    field_errors[field] = [str(messages)]
            
            return Response(
                {
                    'error': 'Validation failed',
                    'message': 'Por favor, corrige los errores en el formulario',
                    'field_errors': field_errors,
                    'errors': field_errors  # Alias for compatibility
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        else:
            # Non-field errors
            error_message = str(error.detail) if hasattr(error, 'detail') else str(error)
            return Response(
                {
                    'error': 'Validation failed',
                    'message': error_message,
                    'field_errors': {},
                    'errors': {}
                },
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @staticmethod
    def handle_permission_error(
        error: PermissionDenied,
        context: Optional[Dict[str, Any]] = None
    ) -> Response:
        """
        Handle permission denied errors with clear messaging.
        
        Args:
            error: The PermissionDenied exception
            context: Additional context for logging
            
        Returns:
            Response with permission error details
        """
        error_context = context or {}
        logger.warning(
            f"🔴 [EXPERIENCE_ERROR] Permission denied: {error.detail}",
            extra={
                'error_type': 'permission',
                'error_detail': str(error.detail),
                **error_context
            }
        )
        
        error_message = str(error.detail) if hasattr(error, 'detail') else 'No tienes permisos para realizar esta acción'
        
        return Response(
            {
                'error': 'Permission denied',
                'message': error_message,
                'field_errors': {},
                'errors': {}
            },
            status=status.HTTP_403_FORBIDDEN
        )
    
    @staticmethod
    def handle_authentication_error(
        error: AuthenticationFailed,
        context: Optional[Dict[str, Any]] = None
    ) -> Response:
        """
        Handle authentication errors (401).
        
        Args:
            error: The AuthenticationFailed exception
            context: Additional context for logging
            
        Returns:
            Response with authentication error details
        """
        error_context = context or {}
        logger.warning(
            f"🔴 [EXPERIENCE_ERROR] Authentication failed: {error.detail}",
            extra={
                'error_type': 'authentication',
                'error_detail': str(error.detail),
                **error_context
            }
        )
        
        error_message = str(error.detail) if hasattr(error, 'detail') else 'Credenciales inválidas o sesión expirada'
        
        return Response(
            {
                'error': 'Authentication failed',
                'message': error_message,
                'field_errors': {},
                'errors': {}
            },
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    @staticmethod
    def handle_database_error(
        error: Exception,
        context: Optional[Dict[str, Any]] = None
    ) -> Response:
        """
        Handle database-related errors (IntegrityError, DatabaseError).
        
        Args:
            error: The database exception
            context: Additional context for logging
            
        Returns:
            Response with database error details
        """
        error_context = context or {}
        logger.error(
            f"🔴 [EXPERIENCE_ERROR] Database error: {str(error)}",
            exc_info=True,
            extra={
                'error_type': 'database',
                'error_detail': str(error),
                **error_context
            }
        )
        
        # Don't expose internal database errors to clients
        return Response(
            {
                'error': 'Database error',
                'message': 'Ocurrió un error al guardar los datos. Por favor, intenta nuevamente.',
                'field_errors': {},
                'errors': {}
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
    @staticmethod
    def handle_generic_error(
        error: Exception,
        context: Optional[Dict[str, Any]] = None,
        user_message: Optional[str] = None
    ) -> Response:
        """
        Handle generic/unexpected errors with proper logging.
        
        Args:
            error: The exception
            context: Additional context for logging
            user_message: Custom message to show to user (optional)
            
        Returns:
            Response with error details
        """
        error_context = context or {}
        logger.error(
            f"🔴 [EXPERIENCE_ERROR] Unexpected error: {str(error)}",
            exc_info=True,
            extra={
                'error_type': 'generic',
                'error_detail': str(error),
                'error_class': error.__class__.__name__,
                **error_context
            }
        )
        
        message = user_message or 'Ocurrió un error inesperado. Por favor, intenta nuevamente.'
        
        return Response(
            {
                'error': 'Internal server error',
                'message': message,
                'field_errors': {},
                'errors': {}
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
    @staticmethod
    def handle_exception(
        error: Exception,
        context: Optional[Dict[str, Any]] = None
    ) -> Response:
        """
        🚀 ENTERPRISE: Main exception handler that routes to appropriate handler.
        
        Args:
            error: The exception to handle
            context: Additional context for logging
            
        Returns:
            Response with appropriate error details
        """
        # Route to specific handlers
        if isinstance(error, ValidationError):
            return ExperienceErrorHandler.handle_validation_error(error, context)
        elif isinstance(error, PermissionDenied):
            return ExperienceErrorHandler.handle_permission_error(error, context)
        elif isinstance(error, AuthenticationFailed):
            return ExperienceErrorHandler.handle_authentication_error(error, context)
        elif isinstance(error, (IntegrityError, DatabaseError)):
            return ExperienceErrorHandler.handle_database_error(error, context)
        else:
            return ExperienceErrorHandler.handle_generic_error(error, context)
    
    @staticmethod
    def format_field_errors(serializer_errors: Dict[str, Any]) -> Dict[str, List[str]]:
        """
        Format serializer errors into a consistent structure.
        
        Args:
            serializer_errors: Errors from serializer.errors
            
        Returns:
            Formatted field errors dictionary
        """
        formatted = {}
        
        for field, messages in serializer_errors.items():
            if isinstance(messages, list):
                formatted[field] = [str(msg) for msg in messages]
            elif isinstance(messages, dict):
                # Nested errors
                formatted[field] = [f"{k}: {v}" for k, v in messages.items()]
            else:
                formatted[field] = [str(messages)]
        
        return formatted



