"""Endurecimiento HTTP: cabeceras de seguridad y límite de tamaño del cuerpo."""

from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Swagger/ReDoc cargan scripts de un CDN: una CSP estricta los rompería, así que no se aplica ahí.
_DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")

_STATIC_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}


class SecurityHeadersMiddleware:
    """Añade cabeceras que mitigan XSS, clickjacking y sniffing de contenido.

    · La API solo devuelve JSON: su CSP (`default-src 'none'`) prohíbe cargar o ejecutar nada,
      así una respuesta manipulada nunca podría ejecutar scripts en el navegador.
    · `Cache-Control: no-store` en la API: tokens y datos personales no se guardan en cachés.
    · HSTS solo en producción (HTTPS).
    """

    def __init__(self, app: ASGIApp, *, hsts: bool = False) -> None:
        self.app = app
        self._hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        is_docs = path.startswith(_DOCS_PATHS)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in _STATIC_HEADERS.items():
                    headers.setdefault(name, value)
                if not is_docs:
                    headers.setdefault(
                        "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'"
                    )
                    headers.setdefault("Cache-Control", "no-store")
                if self._hsts:
                    headers.setdefault(
                        "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
                    )
            await send(message)

        await self.app(scope, receive, send_with_headers)


class _BodyTooLarge(BaseException):  # noqa: N818 - FastAPI captura `Exception` y lo volvería un 400
    """Se superó el límite de bytes mientras se leía el cuerpo. Sube hasta este middleware."""


class BodySizeLimitMiddleware:
    """Rechaza cuerpos mayores a `max_bytes` (413) antes de procesarlos.

    Evita agotar memoria con peticiones gigantes. Revisa `Content-Length` y también cuenta los
    bytes recibidos (por si el cliente envía por trozos sin declarar el tamaño).
    """

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self._max = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = Headers(scope=scope).get("content-length")
        if declared and declared.isdigit() and int(declared) > self._max:
            await self._reject(scope, receive, send)
            return

        received = 0
        response_started = False

        async def counting_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self._max:
                    raise _BodyTooLarge
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, tracking_send)
        except _BodyTooLarge:
            if not response_started:
                await self._reject(scope, receive, send)

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        request = Request(scope, receive)
        response = JSONResponse(
            status_code=413,
            media_type="application/problem+json",
            content={
                "type": "about:blank",
                "title": "Content Too Large",
                "status": 413,
                "detail": f"El cuerpo de la petición supera el máximo de {self._max} bytes.",
                "code": "payload_too_large",
                "instance": request.url.path,
                "request_id": scope.get("state", {}).get("request_id"),
            },
        )
        await response(scope, receive, send)
