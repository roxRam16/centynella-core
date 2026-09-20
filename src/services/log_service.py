"""Consulta de la bitácora."""

from datetime import datetime

from src.database import LogQuery, LogRepository
from src.models import LogEntry, LogLevel, levels_at_or_above


class LogService:
    def __init__(self, logs: LogRepository) -> None:
        self._logs = logs

    async def search(
        self,
        *,
        module: str | None,
        min_level: LogLevel | None,
        event: str | None,
        service: str | None,
        user_id: str | None,
        session_id: str | None,
        request_id: str | None,
        since: datetime | None,
        until: datetime | None,
        text: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[LogEntry], int]:
        """Eventos que cumplen los filtros; `min_level` = ese nivel o superior."""
        query = LogQuery(
            module=module,
            levels=levels_at_or_above(min_level) if min_level else None,
            event=event,
            service=service,
            user_id=user_id,
            session_id=session_id,
            request_id=request_id,
            since=since,
            until=until,
            text=text,
        )
        return await self._logs.search(query, page=page, page_size=page_size)

    async def modules(self) -> list[str]:
        return await self._logs.modules()
