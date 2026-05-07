"""
Custom Exception Classes for MediaTool Trip
Xử lý lỗi chi tiết và tránh xung đột error messages
"""

class MediaToolException(Exception):
    """Base exception class for MediaTool"""
    
    def __init__(self, message, error_code=None, context=None):
        self.message = message
        self.error_code = error_code or 'UNKNOWN_ERROR'
        self.context = context or {}
        super().__init__(self.message)
    
    def to_dict(self):
        """Convert exception to dict for API response"""
        return {
            'error': self.message,
            'error_code': self.error_code,
            'context': self.context
        }
    
    def __str__(self):
        return f"[{self.error_code}] {self.message}"

class Error(MediaToolException):
    """General error class for internal use"""
    
    def __init__(self, message, context=None):
        super().__init__(message, 'ERROR', context)

class ResponseError(MediaToolException):
    """Raised when HTTP response is invalid or indicates an error"""
    
    def __init__(self, message, context=None):
        super().__init__(message, 'RESPONSE_ERROR', context)
class UnauthorizedError(MediaToolException):
    """Raised when authentication fails (e.g. invalid cookies)"""
    
    def __init__(self, message, context=None):
        super().__init__(message, 'UNAUTHORIZED', context)
class NotFoundError(MediaToolException):
    """Raised when requested resource is not found"""
    
    def __init__(self, message, context=None):
        super().__init__(message, 'NOT_FOUND', context)
class RetryExhaustedError(MediaToolException):
    """Raised when all retry attempts are exhausted"""
    
    def __init__(self, message, context=None):
        super().__init__(message, 'RETRY_EXHAUSTED', context)
class ConnectionError(MediaToolException):
    """Raised when connection fails"""
    
    def __init__(self, message, context=None):
        super().__init__(message, 'CONNECTION_ERROR', context)


class URLError(MediaToolException):
    """Raised when URL is invalid or not found"""
    
    def __init__(self, message, context=None):
        super().__init__(message, 'URL_ERROR', context)


class ExtractError(MediaToolException):
    """Raised when extraction fails"""
    
    def __init__(self, message, context=None):
        super().__init__(message, 'EXTRACT_ERROR', context)


class AuthenticationError(MediaToolException):
    """Raised when authentication fails (invalid cookies, etc)"""
    
    def __init__(self, message, context=None):
        super().__init__(message, 'AUTH_ERROR', context)


class RateLimitError(MediaToolException):
    """Raised when rate limit exceeded"""
    
    def __init__(self, message, context=None):
        super().__init__(message, 'RATE_LIMIT_ERROR', context)


class TimeoutError(MediaToolException):
    """Raised when request timeout"""
    
    def __init__(self, message, context=None):
        super().__init__(message, 'TIMEOUT_ERROR', context)


class UnavailableError(MediaToolException):
    """Raised when service is unavailable"""
    
    def __init__(self, message, context=None):
        super().__init__(message, 'SERVICE_UNAVAILABLE', context)


class DataFormatError(MediaToolException):
    """Raised when response data format is invalid"""
    
    def __init__(self, message, context=None):
        super().__init__(message, 'DATA_FORMAT_ERROR', context)


class ConfigError(MediaToolException):
    """Raised when configuration is invalid"""
    
    def __init__(self, message, context=None):
        super().__init__(message, 'CONFIG_ERROR', context)


class PlatformNotSupportedError(MediaToolException):
    """Raised when platform is not supported"""
    
    def __init__(self, platform, context=None):
        message = f"Platform '{platform}' chưa được hỗ trợ"
        super().__init__(message, 'PLATFORM_NOT_SUPPORTED', context or {'platform': platform})


def handle_exception(exc, logger=None):
    """
    Handle exception and return standardized error response
    
    Args:
        exc: Exception object
        logger: Optional logger instance
    
    Returns:
        dict: Error response
    """
    if isinstance(exc, MediaToolException):
        if logger:
            logger.error(f"MediaTool Error: {exc}")
        return exc.to_dict()
    else:
        error_dict = {
            'error': str(exc),
            'error_code': 'INTERNAL_ERROR',
            'context': {}
        }
        if logger:
            logger.error(f"Unexpected Error: {exc}", exc_info=True)
        return error_dict