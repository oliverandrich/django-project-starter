from collections.abc import AsyncIterator, Iterable, Iterator

from asgiref.sync import sync_to_async
from django.contrib.staticfiles.views import serve
from django.http import HttpRequest, HttpResponseBase, StreamingHttpResponse


async def serve_static(request: HttpRequest, path: str) -> HttpResponseBase:
    """staticfiles' serve() for DEBUG, with a body Django's ASGI handler streams without a warning.

    serve() answers with a FileResponse over a synchronous file iterator, and the handler warns
    about every such response. granian serves STATIC_ROOT outside DEBUG.
    """
    response = await sync_to_async(serve)(request, path)
    if isinstance(response, StreamingHttpResponse):
        content = response.streaming_content
        if isinstance(content, Iterable):
            response.streaming_content = _read(iter(content))
    return response


async def _read(chunks: Iterator[bytes]) -> AsyncIterator[bytes]:
    # Each read runs in a thread; the file object stays on the response, which closes it.
    while (chunk := await sync_to_async(next)(chunks, None)) is not None:
        yield chunk
