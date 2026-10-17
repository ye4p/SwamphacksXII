"""Safe errors and bounded retries shared by the scraper modules."""

import time


class ScraperError(Exception):
    """An error whose message is deliberately safe to put in public JSON."""

    def __init__(self, stage, code, message, retryable=False):
        super().__init__(message)
        self.stage, self.code, self.retryable = stage, code, retryable


def error_record(error, stage):
    """Never copy raw SDK exception messages, URLs, headers, or tokens."""
    if isinstance(error, ScraperError):
        return {"stage": error.stage, "code": error.code, "message": str(error)}
    # SDKs use different properties for HTTP status codes.
    status = getattr(error, "status_code", None) or getattr(error, "code", None)
    if not isinstance(status, int):
        status = getattr(getattr(error, "response", None), "status_code", None)
    codes = {401: ("authentication", "API credentials were rejected."),
             403: ("access_denied", "Check API permissions and billing setup."),
             429: ("rate_limit", "API quota or rate limit reached."),
             408: ("timeout", "The service request timed out.")}
    if status in codes:
        code, message = codes[status]
    elif isinstance(status, int) and status >= 500:
        code, message = "service_unavailable", "The service is temporarily unavailable."
    elif 'timeout' in type(error).__name__.lower():
        code, message = "timeout", "The service request timed out."
    elif 'connect' in type(error).__name__.lower():
        code, message = "connection_error", "Could not connect to the service."
    elif isinstance(error, ImportError):
        code, message = "missing_dependency", "A required Python library is not installed."
    elif isinstance(error, OSError):
        code, message = "io_error", "A file or network operation failed."
    else:
        code, message = "unexpected_error", "Unexpected failure; inspect the code for this stage."
    return {"stage": stage, "code": code, "message": message}


def retry_call(operation, attempts=2):
    """Retry only explicitly transient failures, with a short bounded delay."""
    for attempt in range(attempts):
        try:
            return operation()
        except ScraperError as error:
            if not error.retryable or attempt + 1 == attempts:
                raise
            time.sleep(min(2 ** attempt, 2))


def http_failure(stage, status):
    """Turn an HTTP status into a safe, actionable error without its response body."""
    descriptions = {401: "Check the API key.", 403: "Check permissions, billing, or expired image links.",
                    429: "Quota or rate limit reached."}
    return ScraperError(stage, f"http_{status}",
                        f"HTTP {status}. {descriptions.get(status, 'The service rejected the request.')}",
                        status in {408, 429, 500, 502, 503, 504})
