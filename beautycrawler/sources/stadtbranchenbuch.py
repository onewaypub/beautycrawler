"""Stadtbranchenbuch (stadtbranchenbuch.com) — City-Subdomains (hamburg.stadtbranchenbuch.com).

robots.txt sperrt /search, erlaubt aber die Kategorieseiten. Das Listing enthält
die eigene Website der Firma DIREKT als 'Homepage'-Link (keine Detailseiten-
Auflösung nötig). Name/Adresse kommen aus dem eingebetteten JSON-LD (LocalBusiness),
die Website aus dem zugehörigen HTML-Eintrag (div.serp-listing).
"""
from __future__ import annotations

import json
import re
from urllib.parse import urljoin

from ..http_client import HttpClient
from ..models import Business
from .base import Area, Source

# Suchbegriff im Kategorie-Link -> kanonische Kategorie
CATEGORY_KEYWORDS = {
    "Friseur": "Friseur",
    "Kosmetik": "Kosmetik",
    "Nagel": "Maniküre/Nagel",
    "Massage": "Massage",
}
_DETAIL_RE = re.compile(r"/\d+\.html")
_CAT_LINK_RE = re.compile(r"/[A-Za-z]/\d+\.html")


class StadtbranchenbuchSource(Source):
    name = "stadtbranchenbuch"

    def __init__(self, categories: list[str] | None = None):
        self.categories = categories or ["Friseur", "Kosmetik", "Nagel"]

    def _addr_map(self, soup) -> dict:
        """@id (Detailseiten-URL) -> {name, street, postcode, city} aus JSON-LD."""
        out: dict[str, dict] = {}
        for x in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(x.string or "")
            except json.JSONDecodeError:
                continue
            for it in (data if isinstance(data, list) else [data]):
                if not (isinstance(it, dict) and it.get("@type") == "LocalBusiness"):
                    continue
                aid = it.get("@id")
                if not aid:
                    continue
                a = it.get("address", {}) or {}
                out[aid] = {
                    "name": it.get("name"),
                    "street": a.get("streetAddress"),
                    "postcode": a.get("postalCode"),
                    "city": a.get("addressLocality"),
                }
        return out

    def _parse(self, html: str, base: str, category: str, city: str) -> list[Business]:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        amap = self._addr_map(soup)
        out: list[Business] = []
        for el in soup.select("div.serp-listing"):
            detail = el.find("a", href=_DETAIL_RE)
            if not detail:
                continue
            durl = urljoin(base, detail["href"])
            info = amap.get(durl, {})
            name = info.get("name") or detail.get_text(" ", strip=True)
            if not name:
                continue
            website = None
            for a in el.find_all("a", href=True):
                if a.get_text(strip=True).lower() == "homepage" and a["href"].startswith("http"):
                    website = a["href"]
                    break
            out.append(Business(
                name=name.strip(),
                categories=[category],
                website=website,
                street=info.get("street"),
                postcode=info.get("postcode"),
                city=info.get("city") or city,
                sources=[self.name],
                detail_url=durl,
            ))
        return out

    def discover(self, client: HttpClient, area: Area, limit: int | None = None) -> list[Business]:
        cityslug = (area.city or area.name).strip().lower().replace(" ", "-")
        base = f"https://{cityslug}.stadtbranchenbuch.com/"
        home = client.get(base)
        if not home.ok or not home.text:
            return []

        from bs4 import BeautifulSoup

        soup = BeautifulSoup(home.text, "lxml")
        results: list[Business] = []
        for kw in self.categories:
            category = CATEGORY_KEYWORDS.get(kw, "Kosmetik")
            link = None
            for a in soup.find_all("a", href=True):
                if kw.lower() in a.get_text(" ", strip=True).lower() and _CAT_LINK_RE.search(a["href"]):
                    link = urljoin(base, a["href"])
                    break
            if not link:
                continue
            resp = client.get(link)
            if not resp.ok:
                continue
            results.extend(self._parse(resp.text, base, category, area.city or area.name))
            if limit and len(results) >= limit:
                return results[:limit]
        return results
