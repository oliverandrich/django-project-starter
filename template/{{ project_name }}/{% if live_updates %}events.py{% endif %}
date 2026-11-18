"""Who may read which server-sent event topic. django-pg-sse runs the streams.

PG_SSE["CAN_SUBSCRIBE"] in settings.py points here.
"""

from django.http import HttpRequest
from django_pg_sse.permissions import can_subscribe as default_can_subscribe


def can_subscribe(request: HttpRequest, topic: str) -> bool:
    """Decides whether the requesting user may receive the events of `topic`.

    The default opens `public:` topics to everyone and `user:<pk>` to that user.
    Every other kind stays closed. Add a case for each kind of topic the project adds.
    It runs when a stream opens; call close_streams() after taking access away.
    """
    # kind, _, key = topic.partition(":")
    # if kind == "room":
    #     return Membership.objects.filter(room=key, user=request.user.pk).exists()
    return default_can_subscribe(request, topic)
