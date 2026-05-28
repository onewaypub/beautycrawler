"""Gemeinsame Typen für Discovery-Quellen."""
from __future__ import annotations

from dataclasses import dataclass

from ..http_client import HttpClient
from ..models import Business


@dataclass
class Area:
    """Suchgebiet. bbox = (süd, west, nord, ost) in WGS84-Grad; city = Klartextname."""
    name: str
    bbox: tuple[float, float, float, float] | None = None
    city: str | None = None

    def __post_init__(self):
        if self.city is None:
            self.city = self.name


class Source:
    """Basisklasse für eine Discovery-Quelle."""

    name: str = "base"

    def discover(self, client: HttpClient, area: Area, limit: int | None = None) -> list[Business]:
        raise NotImplementedError
