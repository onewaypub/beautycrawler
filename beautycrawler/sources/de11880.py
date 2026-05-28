"""11880.com — Branchenverzeichnis. Listing liefert sauberes JSON-LD (Name, Adresse, Tel).

Die eigene Website der Firma steht NICHT im Listing (nur die 11880-Detailseite);
sie wird später in der Pipeline per Suchmaschine aufgelöst.
"""
from __future__ import annotations

import json

from ..http_client import HttpClient
from ..models import Business
from .base import Area, Source

# 11880-Branchen-Slug -> kanonische Kategorie
SLUG_CATEGORY = {
    "friseur": "Friseur",
    "kosmetikstudio": "Kosmetik",
    "nagelstudio": "Maniküre/Nagel",
    "fusspflege": "Pediküre/Fußpflege",
    "massage": "Massage",
    "visagist": "Visagistik",
}


class Elf880Source(Source):
    name = "11880"

    def __init__(self, slugs: list[str] | None = None, max_pages: int = 1):
        self.slugs = slugs or ["friseur", "kosmetikstudio", "nagelstudio"]
        self.max_pages = max_pages

    def _parse_listing(self, html: str, category: str, city: str) -> list[Business]:
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
            main = data.get("mainEntity") if isinstance(data, dict) else None
            if not (isinstance(main, dict) and main.get("@type") == "ItemList"):
                continue
            for el in main.get("itemListElement", []):
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
                    detail_url=item.get("url"),  # 11880-Detailseite -> enthält echte Website
                ))
        return out

    def discover(self, client: HttpClient, area: Area, limit: int | None = None) -> list[Business]:
        city = (area.city or area.name).lower().replace(" ", "-")
        results: list[Business] = []
        for slug in self.slugs:
            category = SLUG_CATEGORY.get(slug, "Kosmetik")
            for page in range(1, self.max_pages + 1):
                url = f"https://www.11880.com/suche/{slug}/{city}"
                if page > 1:
                    url += f"?page={page}"
                resp = client.get(url)
                if not resp.ok:
                    break
                batch = self._parse_listing(resp.text, category, area.city or area.name)
                if not batch:
                    break
                results.extend(batch)
                if limit and len(results) >= limit:
                    return results[:limit]
        return results
