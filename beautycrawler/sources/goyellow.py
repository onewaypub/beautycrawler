"""GoYellow (goyellow.de) — Branchenverzeichnis; robots.txt erlaubt /suche.

Listing nutzt schema.org-Microdata (itemtype=LocalBusiness), KEIN JSON-LD.
Eigene Website der Firma steht auf der Detailseite -> websearch-Auflösung.
"""
from __future__ import annotations

from ..http_client import HttpClient
from ..models import Business
from .base import Area, Source

BASE = "https://www.goyellow.de"

SLUG_CATEGORY = {
    "friseur": "Friseur",
    "kosmetikstudio": "Kosmetik",
    "nagelstudio": "Maniküre/Nagel",
    "fusspflege": "Pediküre/Fußpflege",
    "massage": "Massage",
}


def _prop(el, name: str) -> str | None:
    n = el.select_one(f'[itemprop="{name}"]')
    if not n:
        return None
    return n.get("content") or n.get("href") or (n.get_text(" ", strip=True) or None)


class GoYellowSource(Source):
    name = "goyellow"

    def __init__(self, slugs: list[str] | None = None):
        self.slugs = slugs or ["friseur", "kosmetikstudio", "nagelstudio"]

    def _parse(self, html: str, category: str, city: str) -> list[Business]:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        out: list[Business] = []
        for el in soup.select('[itemtype*="LocalBusiness"]'):
            name_el = el.select_one('[itemprop="name"]')
            name = name_el.get_text(" ", strip=True) if name_el else None
            if not name:
                continue
            url_el = el.select_one('[itemprop="url"]')
            detail = url_el.get("href") if url_el else None
            if detail and detail.startswith("/"):
                detail = BASE + detail
            out.append(Business(
                name=name.strip(),
                categories=[category],
                website=None,
                street=_prop(el, "streetAddress"),
                postcode=_prop(el, "postalCode"),
                city=_prop(el, "addressLocality") or city,
                phone=_prop(el, "telephone"),
                sources=[self.name],
                detail_url=detail,
            ))
        return out

    def discover(self, client: HttpClient, area: Area, limit: int | None = None) -> list[Business]:
        city = (area.city or area.name).strip().lower().replace(" ", "-")
        results: list[Business] = []
        for slug in self.slugs:
            category = SLUG_CATEGORY.get(slug, "Kosmetik")
            resp = client.get(f"{BASE}/suche/{slug}/{city}")
            if not resp.ok:
                continue
            results.extend(self._parse(resp.text, category, area.city or area.name))
            if limit and len(results) >= limit:
                return results[:limit]
        return results
