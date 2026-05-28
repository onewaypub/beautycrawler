"""Kommandozeile für den beautycrawler."""
from __future__ import annotations

import argparse
import logging

from .http_client import HttpClient
from .logging_setup import setup_logging
from .pipeline import run
from .sources import REGISTRY
from .sources.base import Area
from .sources.de11880 import Elf880Source
from .sources.osm import OsmSource

# Vordefinierte Stadt-Bounding-Boxes (süd, west, nord, ost).
AREAS: dict[str, tuple[float, float, float, float]] = {
    "hamburg": (53.39, 9.73, 53.74, 10.33),
    "berlin": (52.34, 13.09, 52.68, 13.76),
    "muenchen": (48.06, 11.36, 48.25, 11.72),
    "koeln": (50.83, 6.77, 51.09, 7.16),
    "frankfurt": (50.02, 8.47, 50.23, 8.80),
    # kleines Test-Sample in Hamburg-Zentrum
    "hamburg-mitte": (53.54, 9.95, 53.59, 10.03),
}


def build_sources(names: list[str]) -> list:
    out = []
    for n in names:
        if n == "osm":
            out.append(OsmSource())
        elif n == "11880":
            out.append(Elf880Source())
        elif n in REGISTRY:
            out.append(REGISTRY[n]())
        else:
            print(f"[warn] unbekannte Quelle: {n}")
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description="Beauty/Salon-B2B-Crawler (DE)")
    p.add_argument("--city", default="hamburg-mitte", help="Stadt-Schlüssel aus AREAS oder beliebiger Name (mit --bbox)")
    p.add_argument("--bbox", help="Bounding-Box 'sued,west,nord,ost' (überschreibt --city-bbox)")
    p.add_argument("--sources", default="osm,11880,dasoertliche,goyellow,stadtbranchenbuch,overture",
                   help="Komma-Liste: osm,11880,dasoertliche,goyellow,stadtbranchenbuch,overture")
    p.add_argument("--limit", type=int, default=25, help="Max. Firmen für die teuren Schritte (0 = unbegrenzt)")
    p.add_argument("--sizes", default="3-5,6-10,11+",
                   help="Zu behaltende Größen-Buckets (Komma). Standard ohne 'unbekannt' und '1-2'.")
    p.add_argument("--min-confidence", default="mittel", choices=["niedrig", "mittel", "hoch"],
                   help="Mindest-Konfidenz der Größenschätzung (Standard: mittel = niedrig wird verworfen)")
    p.add_argument("--no-resolve", action="store_true", help="Website-Auflösung (Detailseite) deaktivieren")
    p.add_argument("--use-ddg", action="store_true", help="DuckDuckGo-Websuche als Fallback (langsam, kann blockiert werden)")
    p.add_argument("--out", default="output/salons.csv", help="CSV-Ausgabepfad")
    p.add_argument("--delay", type=float, default=1.5, help="Mindestabstand pro Host (Sekunden)")
    p.add_argument("--timeout", type=float, default=15.0)
    p.add_argument("--quiet", action="store_true", help="Nur Warnungen + Endbericht in der Konsole")
    p.add_argument("--no-log-file", action="store_true", help="Keine Logdatei schreiben")
    args = p.parse_args(argv)

    logger, log_path = setup_logging(
        level=logging.WARNING if args.quiet else logging.INFO,
        to_file=not args.no_log_file,
    )

    city_key = args.city.lower()
    if args.bbox:
        s, w, n, e = (float(x) for x in args.bbox.split(","))
        bbox = (s, w, n, e)
    else:
        bbox = AREAS.get(city_key)
    city_name = city_key.split("-")[0]
    area = Area(name=city_name, bbox=bbox, city=city_name)

    client = HttpClient(default_delay=args.delay, timeout=args.timeout)
    sources = build_sources([s.strip() for s in args.sources.split(",") if s.strip()])

    logger.info("=" * 60)
    logger.info("beautycrawler — Start")
    logger.info("  Gebiet=%s  bbox=%s", area.name, bbox)
    logger.info("  Quellen=%s  Limit=%s  Website-Auflösung=%s",
                [s.name for s in sources], args.limit or "∞", "an" if not args.no_resolve else "aus")
    if log_path:
        logger.info("  Logdatei: %s", log_path)
    logger.info("  CSV-Ausgabe: %s", args.out)
    logger.info("=" * 60)

    keep_sizes = {s.strip() for s in args.sizes.split(",") if s.strip()}
    _conf_levels = {
        "niedrig": {"niedrig", "mittel", "hoch"},
        "mittel": {"mittel", "hoch"},
        "hoch": {"hoch"},
    }
    keep_confidences = _conf_levels[args.min_confidence]
    logger.info("  Filter: Größen=%s  Mindest-Konfidenz=%s", sorted(keep_sizes), args.min_confidence)

    metrics = run(
        sources, area, client,
        limit=(args.limit or None),
        keep_sizes=keep_sizes,
        keep_confidences=keep_confidences,
        resolve_missing=not args.no_resolve,
        use_ddg=args.use_ddg,
        out_path=args.out,
    )

    report = metrics.report()
    print(report)  # immer in der Konsole, auch bei --quiet
    if log_path:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("\n" + report + "\n")
        print(f"\n[Logdatei: {log_path}]")


if __name__ == "__main__":
    main()
