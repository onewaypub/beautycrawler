"""Overture Maps — offener Geo-Datensatz (places), per DuckDB auf Remote-Parquet (S3).

Andere Datenherkunft als die Verzeichnisse/OSM -> findet zusätzliche Salons.
Anonymer Zugriff auf den öffentlichen Bucket (kein AWS-Account nötig).
Benötigt das Paket 'duckdb' (optional; ohne duckdb liefert die Quelle nichts).
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from ..http_client import HttpClient
from ..models import Business
from ..websearch import _is_blocked
from .base import Area, Source

S3_BUCKET = "overturemaps-us-west-2"
PINNED_RELEASE = "2026-05-20.0"  # Fallback, falls Auto-Erkennung fehlschlägt

# Overture-Kategorie -> unsere Kategorie (nur relevante Beauty-Branchen)
CATEGORY_MAP = {
    "hair_salon": "Friseur", "barber": "Friseur", "hair_stylist": "Friseur",
    "hair_extensions": "Friseur", "hair_replacement": "Friseur", "hair_loss_center": "Friseur",
    "beauty_salon": "Kosmetik", "beauty_and_spa": "Kosmetik", "laser_hair_removal": "Kosmetik",
    "waxing": "Kosmetik", "hair_removal": "Kosmetik", "medical_spa": "Kosmetik",
    "eyelash_service": "Visagistik", "eyebrow_service": "Visagistik",
    "nail_salon": "Maniküre/Nagel",
    "massage_therapy": "Massage", "massage": "Massage", "spas": "Massage",
    "day_spa": "Massage", "health_spa": "Massage",
}


class OvertureSource(Source):
    name = "overture"

    def __init__(self, release: str | None = None):
        self._release = release

    def _latest_release(self) -> str:
        """Neueste Release-Version aus dem öffentlichen S3-Listing; sonst Fallback."""
        try:
            import requests

            url = f"https://{S3_BUCKET}.s3.us-west-2.amazonaws.com/?list-type=2&prefix=release/&delimiter=/"
            r = requests.get(url, timeout=20)
            rels = re.findall(r"<Prefix>release/([^<]+?)/</Prefix>", r.text)
            return max(rels) if rels else PINNED_RELEASE
        except Exception:
            return PINNED_RELEASE

    def _pick_website(self, websites) -> str | None:
        if not websites:
            return None
        for w in websites:
            if not w:
                continue
            host = urlparse(w if "://" in w else "http://" + w).netloc
            if not _is_blocked(host):
                return w
        return None

    def discover(self, client: HttpClient, area: Area, limit: int | None = None) -> list[Business]:
        if not area.bbox:
            return []
        try:
            import duckdb
        except ImportError:
            return []

        if self._release is None:
            self._release = self._latest_release()
        s, w, n, e = area.bbox
        cats = ", ".join(f"'{c}'" for c in CATEGORY_MAP)
        path = f"s3://{S3_BUCKET}/release/{self._release}/theme=places/type=place/*.parquet"
        query = f"""
            SELECT names.primary AS name, categories.primary AS cat, websites,
                   addresses[1].freeform AS street,
                   addresses[1].postcode AS postcode,
                   addresses[1].locality AS city
            FROM read_parquet('{path}', hive_partitioning=1)
            WHERE bbox.xmin BETWEEN {w} AND {e}
              AND bbox.ymin BETWEEN {s} AND {n}
              AND categories.primary IN ({cats})
              AND websites IS NOT NULL AND len(websites) > 0
        """
        try:
            con = duckdb.connect()
            con.execute("INSTALL httpfs; LOAD httpfs; SET s3_region='us-west-2';")
            rows = con.execute(query).fetchall()
            con.close()
        except Exception:
            return []

        out: list[Business] = []
        for name, cat, websites, street, postcode, city in rows:
            if not name:
                continue
            website = self._pick_website(websites)
            if not website:
                continue  # nur Einträge mit nutzbarer eigener Website
            out.append(Business(
                name=name.strip(),
                categories=[CATEGORY_MAP.get(cat, "Kosmetik")],
                website=website,
                street=street,
                postcode=postcode,
                city=city or area.city,
                sources=[self.name],
            ))
            if limit and len(out) >= limit:
                break
        return out
