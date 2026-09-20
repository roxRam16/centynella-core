"""Middleware de correlación: un `X-Request-ID` por petición y su contexto."""

import re
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.middlewares.context import RequestContext, reset_context, set_context

REQUEST_ID_HEADER = "X-Request-ID"
# Solo se acepta un id entrante "seguro" (evita inyectar basura en logs y cabeceras).
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class RequestIdMiddleware:
    """Reutiliza el `X-Request-ID` del cliente o genera uno, y lo devuelve en la respuesta.

    Se guarda en `request.state.request_id` para que los handlers de error puedan citarlo y en
    el `RequestContext` para que la bitácora lo enlace a todo lo ocurrido en la petición.
    Implementado como ASGI puro (más liviano y predecible que BaseHTTPMiddleware).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        incoming = headers.get(REQUEST_ID_HEADER, "")
        request_id = incoming if _SAFE_REQUEST_ID.match(incoming) else uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id

        client = scope.get("client")
        token = set_context(
            RequestContext(
                request_id=request_id,
                ip=client[0] if client else None,
                user_agent=(headers.get("user-agent") or "")[:255] or None,
                method=scope.get("method"),
                path=scope.get("path"),
            )
        )

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            reset_context(token)
