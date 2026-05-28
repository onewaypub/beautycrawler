"""OpenStreetMap via Overpass API. Strukturierte Basisquelle (Website oft direkt dabei)."""
from __future__ import annotations

import json

from ..http_client import HttpClient
from ..models import Business
from .base import Area, Source

OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"


def _categories_from_tags(tags: dict) -> list[str]:
    cats: list[str] = []
    shop = tags.get("shop", "")
    craft = tags.get("craft", "")
    beauty = tags.get("beauty", "")
    if shop == "hairdresser" or craft == "hairdresser":
        cats.append("Friseur")
    if shop == "massage":
        cats.append("Massage")
    if shop == "beauty" and not beauty:
        cats.append("Kosmetik")
    # beauty=* Subtags differenzieren
    bset = {b.strip() for b in beauty.replace(";", ",").split(",") if b.strip()}
    if {"nails", "nail", "manicure"} & bset:
        cats.append("Maniküre/Nagel")
    if {"pedicure", "foot_care", "foot"} & bset:
        cats.append("Pediküre/Fußpflege")
    if {"cosmetics", "skin_care", "facial", "kosmetik"} & bset:
        cats.append("Kosmetik")
    if {"massage", "spa"} & bset:
        cats.append("Massage")
    if {"make_up", "makeup", "visagist"} & bset:
        cats.append("Visagistik")
    if shop == "beauty" and beauty and not cats:
        cats.append("Kosmetik")
    return list(dict.fromkeys(cats)) or (["Kosmetik"] if shop == "beauty" else [])


def _audience_from_tags(tags: dict) -> str | None:
    female = tags.get("female") == "yes"
    male = tags.get("male") == "yes"
    if tags.get("unisex") == "yes" or (female and male):
        return "Unisex"
    if female:
        return "Damen"
    if male:
        return "Herren"
    return None


class OsmSource(Source):
    name = "osm"

    def _build_query(self, bbox: tuple[float, float, float, float]) -> str:
        s, w, n, e = bbox
        b = f"{s},{w},{n},{e}"
        return (
            "[out:json][timeout:90];("
            f'nwr["shop"="hairdresser"]({b});'
            f'nwr["craft"="hairdresser"]({b});'
            f'nwr["shop"="beauty"]({b});'
            f'nwr["shop"="massage"]({b});'
            f'nwr["beauty"]({b});'
            ");out center tags;"
        )

    def discover(self, client: HttpClient, area: Area, limit: int | None = None) -> list[Business]:
        if not area.bbox:
            return []
        query = self._build_query(area.bbox)
        resp = client.get(
            OVERPASS_ENDPOINT, method="POST", data={"data": query},
            respect_robots=False, use_cache=True,
        )
        if not resp.ok:
            return []
        try:
            payload = json.loads(resp.text)
        except json.JSONDecodeError:
            return []

        out: list[Business] = []
        for el in payload.get("elements", []):
            tags = el.get("tags", {})
            name = tags.get("name") or tags.get("operator")
            if not name:
                continue
            cats = _categories_from_tags(tags)
            if not cats:
                continue
            website = (
                tags.get("website") or tags.get("contact:website")
                or tags.get("url") or tags.get("contact:url")
            )
            biz = Business(
                name=name.strip(),
                categories=cats,
                website=website,
                street=" ".join(p for p in [tags.get("addr:street"), tags.get("addr:housenumber")] if p) or None,
                postcode=tags.get("addr:postcode"),
                city=tags.get("addr:city") or area.city,
                phone=tags.get("phone") or tags.get("contact:phone"),
                sources=[self.name],
                opening_hours=tags.get("opening_hours"),
                audience=_audience_from_tags(tags),
            )
            out.append(biz)
            if limit and len(out) >= limit:
                break
        return out
