"""Contexto de la petición en curso (quién, desde dónde, qué sesión).

Se guarda en un `ContextVar` para que CUALQUIER parte del código —servicios, repositorios, el
logger de eventos— sepa a qué petición y usuario pertenece lo que está ocurriendo, sin pasar
parámetros por todas las funciones.

El objeto es MUTABLE a propósito: el middleware lo crea al entrar la petición y la dependencia
de autenticación lo completa después con `user_id` y `session_id`; como todos comparten el mismo
objeto, el log de acceso (al final de la petición) ve esos datos aunque el ContextVar se haya
copiado entre tareas.
"""

from contextvars import ContextVar
from dataclasses import dataclass


@dataclass
class RequestContext:
    request_id: str | None = None
    user_id: str | None = None
    session_id: str | None = None
    ip: str | None = None
    user_agent: str | None = None
    method: str | None = None
    path: str | None = None


_current: ContextVar[RequestContext | None] = ContextVar("request_context", default=None)


def get_context() -> RequestContext:
    """Contexto actual, o uno vacío si se llama fuera de una petición (arranque, tareas)."""
    return _current.get() or RequestContext()


def set_context(context: RequestContext):
    """Activa `context`; devuelve el token para restaurar el anterior con `reset_context`."""
    return _current.set(context)


def reset_context(token) -> None:
    _current.reset(token)


def bind_user(user_id: str | None, session_id: str | None) -> None:
    """Asocia usuario y sesión a la petición en curso (lo hace la autenticación)."""
    context = _current.get()
    if context is not None:
        context.user_id = user_id
        context.session_id = session_id
