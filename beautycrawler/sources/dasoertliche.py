"""Das Örtliche (dasoertliche.de) — Branchenverzeichnis; robots.txt erlaubt alles.

Listing-Seite (/Themen/<Branche>/<Stadt>.html) liefert die Einträge als JSON-LD
(ItemList). Die eigene Website der Firma steht auf der Detailseite und wird – wie
bei 11880 – über websearch.website_from_detail_page aufgelöst.
"""
from __future__ import annotations

import json

from ..http_client import HttpClient
from ..models import Business
from .base import Area, Source

# Das-Örtliche-Branchen-Slug (Teil der URL) -> kanonische Kategorie
SLUG_CATEGORY = {
    "Friseur": "Friseur",
    "Kosmetikstudio": "Kosmetik",
    "Nagelstudio": "Maniküre/Nagel",
    "Fusspflege": "Pediküre/Fußpflege",
    "Massage": "Massage",
}


class DasOertlicheSource(Source):
    name = "dasoertliche"

    def __init__(self, slugs: list[str] | None = None):
        self.slugs = slugs or ["Friseur", "Kosmetikstudio", "Nagelstudio"]

    def _parse(self, html: str, category: str, city: str) -> list[Business]:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        out: list[Business] = []
        for tag in soup.find_all("script", type="application/ld+json"):
            raw = tag.string or tag.get_text()
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not (isinstance(data, dict) and data.get("@type") == "ItemList"):
                continue
            for el in data.get("itemListElement", []):
                item = el.get("item", {}) if isinstance(el, dict) else {}
                name = item.get("name")
                if not name:
                    continue
                addr = item.get("address", {}) or {}
                out.append(Business(
                    name=name.strip(),
                    categories=[category],
                    website=None,
                    street=addr.get("streetAddress"),
                    postcode=addr.get("postalCode"),
                    city=addr.get("addressLocality") or city,
                    phone=item.get("telephone"),
                    sources=[self.name],
                    detail_url=item.get("url"),
                ))
        return out

    def discover(self, client: HttpClient, area: Area, limit: int | None = None) -> list[Business]:
        city = (area.city or area.name).strip().title().replace(" ", "-")
        results: list[Business] = []
        for slug in self.slugs:
            category = SLUG_CATEGORY.get(slug, "Kosmetik")
            url = f"https://www.dasoertliche.de/Themen/{slug}/{city}.html"
            resp = client.get(url)
            if not resp.ok:
                continue
            results.extend(self._parse(resp.text, category, area.city or area.name))
            if limit and len(results) >= limit:
                return results[:limit]
        return results
