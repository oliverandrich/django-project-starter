"""structlog setup and the trimming of django-structlog's request lines.

The project writes no access log. A request line carries only the method and the path:
a query string can hold a token, and the user agent identifies the visitor.
"""

from typing import Any

import structlog
from django.http import HttpRequest
from django_structlog import middlewares, signals


def request_line(request: HttpRequest) -> str:
    return f"{request.method} {request.path}"


def request_without_query(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Shorten a request object to its method and path.

    django.request and django.security pass the request as `extra`. Its repr includes the
    query string.
    """
    request = event_dict.get("request")
    if isinstance(request, HttpRequest):
        event_dict["request"] = request_line(request)
    return event_dict


# Run for records from structlog and from the standard library alike.
SHARED_PROCESSORS: list[Any] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_logger_name,
    structlog.stdlib.add_log_level,
    structlog.stdlib.ExtraAdder(),
    request_without_query,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
]


def configure() -> None:
    """Route structlog through the standard library, whose LOGGING formats every record."""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *SHARED_PROCESSORS,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.UnicodeDecoder(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def formatter(renderer: Any) -> dict[str, Any]:
    """A LOGGING formatter entry that renders every record with `renderer`."""
    return {
        "()": structlog.stdlib.ProcessorFormatter,
        "foreign_pre_chain": SHARED_PROCESSORS,
        "processors": [
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            renderer,
        ],
    }


class RequestMiddleware(middlewares.RequestMiddleware):
    """django-structlog's middleware, with request lines of method and path only."""

    format_request = staticmethod(request_line)


def _drop_user_agent(log_kwargs: dict[str, Any], **kwargs: Any) -> None:
    log_kwargs.pop("user_agent", None)


def connect() -> None:
    signals.bind_extra_request_metadata.connect(_drop_user_agent, dispatch_uid="log_config")
