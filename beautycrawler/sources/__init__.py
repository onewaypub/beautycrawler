"""Discovery-Quellen. Jede Quelle implementiert das Source-Interface aus base.py."""
from .base import Area, Source
from .osm import OsmSource
from .de11880 import Elf880Source

# Registry: Name -> Quellen-Klasse. Inkrementell erweiterbar.
REGISTRY: dict[str, type[Source]] = {
    OsmSource.name: OsmSource,
    Elf880Source.name: Elf880Source,
}

__all__ = ["Area", "Source", "OsmSource", "Elf880Source", "REGISTRY"]
