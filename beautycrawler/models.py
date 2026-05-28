"""Datenmodell für gefundene Unternehmen + Normalisierungs-/Dedupe-Helfer."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import urlparse

# Branchen, die uns interessieren (kanonische Labels).
CATEGORIES = [
    "Friseur",
    "Kosmetik",
    "Maniküre/Nagel",
    "Pediküre/Fußpflege",
    "Massage",
    "Visagistik",
]

# Rechtsform-/Zusatz-Tokens, die beim Namensvergleich ignoriert werden.
_LEGAL_TOKENS = {
    "gmbh", "ug", "haftungsbeschränkt", "co", "kg", "ohg", "gbr", "ev", "e.v",
    "mbh", "ag", "ek", "e.k", "inh", "inhaber", "inhaberin", "salon", "studio",
    "the", "der", "die", "das", "und", "and", "&",
}

CSV_FIELDS = [
    "firmenname",
    "bereiche",
    "webseite",
    "geschaeftsfuehrer_inhaber",
    "adresse",
    "email",
    "fax",
    "ust_idnr",
    "geschaetzte_mitarbeiter",
    "groessen_konfidenz",
    "groessen_basis",
    "quelle",
    "stand",
]


def normalize_name(name: str) -> str:
    """Firmenname auf Vergleichsform reduzieren (klein, ohne Rechtsform/Sonderzeichen)."""
    if not name:
        return ""
    s = name.lower()
    s = s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    tokens = [t for t in s.split() if t and t not in _LEGAL_TOKENS]
    return " ".join(tokens)


def normalize_domain(url: str | None) -> str:
    """Registrierbare Domain aus URL (ohne www, Schema, Pfad)."""
    if not url:
        return ""
    u = url.strip()
    if not u.startswith(("http://", "https://")):
        u = "http://" + u
    try:
        host = urlparse(u).netloc.lower()
    except ValueError:
        return ""
    host = host.split("@")[-1].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host


@dataclass
class Business:
    name: str
    categories: list[str] = field(default_factory=list)
    website: str | None = None
    street: str | None = None
    postcode: str | None = None
    city: str | None = None
    phone: str | None = None
    sources: list[str] = field(default_factory=list)
    detail_url: str | None = None  # Verzeichnis-Detailseite (zur Website-Auflösung)

    # aus dem Impressum extrahiert
    owner: str | None = None
    email: str | None = None
    fax: str | None = None
    vat_id: str | None = None
    impressum_url: str | None = None
    impressum_address: str | None = None

    # Größenschätzung
    size_estimate: str | None = None
    size_confidence: str | None = None
    size_basis: str | None = None

    # Meta / Diagnose
    website_status: str | None = None  # "ok" | "dead" | "no_website" | "blocked"
    retrieved_at: str = field(default_factory=lambda: date.today().isoformat())

    def dedupe_key(self) -> str:
        """Schlüssel zur Zusammenführung: Domain bevorzugt, sonst Name+PLZ/Stadt."""
        dom = normalize_domain(self.website)
        if dom:
            return f"dom:{dom}"
        loc = self.postcode or (self.city or "").lower()
        return f"nm:{normalize_name(self.name)}|{loc}"

    @property
    def address(self) -> str:
        parts = []
        if self.street:
            parts.append(self.street)
        plz_city = " ".join(p for p in [self.postcode, self.city] if p)
        if plz_city:
            parts.append(plz_city)
        return ", ".join(parts)

    def merge(self, other: "Business") -> None:
        """Felder eines Duplikats hineinmischen (vorhandene Werte gewinnen)."""
        for src in other.sources:
            if src not in self.sources:
                self.sources.append(src)
        for cat in other.categories:
            if cat not in self.categories:
                self.categories.append(cat)
        for attr in (
            "website", "street", "postcode", "city", "phone", "owner",
            "email", "fax", "vat_id", "impressum_url", "impressum_address", "detail_url",
        ):
            if not getattr(self, attr) and getattr(other, attr):
                setattr(self, attr, getattr(other, attr))

    def to_csv_row(self) -> dict:
        return {
            "firmenname": self.name or "",
            "bereiche": "; ".join(self.categories),
            "webseite": self.website or "",
            "geschaeftsfuehrer_inhaber": self.owner or "",
            "adresse": self.impressum_address or self.address,
            "email": self.email or "",
            "fax": self.fax or "",
            "ust_idnr": self.vat_id or "",
            "geschaetzte_mitarbeiter": self.size_estimate or "",
            "groessen_konfidenz": self.size_confidence or "",
            "groessen_basis": self.size_basis or "",
            "quelle": "; ".join(self.sources),
            "stand": self.retrieved_at,
        }
