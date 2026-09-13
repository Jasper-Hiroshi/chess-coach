from dataclasses import dataclass
from typing import Any, Literal, Protocol


@dataclass(frozen=True)
class ArchiveRef:
    url: str
    month: str


@dataclass(frozen=True)
class ArchiveFetchResult:
    status: Literal["ok", "not_modified"]
    games: list[dict[str, Any]]
    etag: str | None
    last_modified: str | None


class GameSource(Protocol):
    def list_archives(self, username: str) -> list[ArchiveRef]: ...
    def fetch_archive(self, archive: ArchiveRef, *, etag: str | None, last_modified: str | None) -> ArchiveFetchResult: ...


class ChessEngine(Protocol):
    def analyze(self, fen: str, *, nodes: int, multipv: int, root_moves: tuple[str, ...] = ()) -> list[dict[str, Any]]: ...


class OpeningExplorer(Protocol):
    def query(self, fen: str, *, source: Literal["masters", "lichess"], ratings: tuple[int, ...] = (), speeds: tuple[str, ...] = ()) -> dict[str, Any]: ...


class ExplanationRenderer(Protocol):
    def render(self, facts: dict[str, Any]) -> str: ...

