"""Discovery-Quellen. Jede Quelle implementiert das Source-Interface aus base.py."""
from .base import Area, Source
from .dasoertliche import DasOertlicheSource
from .de11880 import Elf880Source
from .osm import OsmSource

# Registry: Name -> Quellen-Klasse. Inkrementell erweiterbar.
REGISTRY: dict[str, type[Source]] = {
    OsmSource.name: OsmSource,
    Elf880Source.name: Elf880Source,
    DasOertlicheSource.name: DasOertlicheSource,
}

__all__ = ["Area", "Source", "OsmSource", "Elf880Source", "DasOertlicheSource", "REGISTRY"]
