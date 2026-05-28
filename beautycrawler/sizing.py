"""Mitarbeiterzahl/Firmengröße schätzen — mit Konfidenz und nachvollziehbarer Basis.

Signale (von stark zu schwach):
1. Team-/Über-uns-Seite: Anzahl genannter Personen (Name neben Rollen-Stichwort).
2. Mehrere Geschäftsführer/Inhaber im Impressum.
3. Rechtsform (GmbH/AG deuten auf größeren Betrieb).
Die Schätzung ist bewusst grob und als Bucket ausgegeben; Konfidenz spiegelt die
Signalstärke wider.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .http_client import HttpClient

_ROLE = re.compile(
    r"\b(?:Friseur(?:in|meister(?:in)?)?|Stylist(?:in)?|Coloristin?|Barber|"
    r"Kosmetiker(?:in)?|Nageldesigner(?:in)?|Nagelstylist(?:in)?|Masseur(?:in)?|"
    r"Visagist(?:in)?|Heilpraktiker(?:in)?|Inhaber(?:in)?|Gesch[äa]ftsf[üu]hrer(?:in)?|"
    r"Auszubildende[rs]?|Azubi|Meister(?:in)?|Top-Stylist(?:in)?|Junior-?Stylist(?:in)?)\b",
    re.IGNORECASE,
)
_NAME = re.compile(r"[A-ZÄÖÜ][a-zäöüß]+(?:[-\s]+[A-ZÄÖÜ][a-zäöüß]+){0,2}")

TEAM_HINTS = ("team", "über-uns", "ueber-uns", "ueberuns", "ueber_uns", "das-team",
              "unser-team", "mitarbeiter", "ueber", "about", "salon")


def detect_legal_form(name: str, impressum_text: str) -> str | None:
    blob = f"{name} {impressum_text}".lower()
    if re.search(r"\bag\b", blob) and "gmbh" not in blob:
        return "AG"
    if "gmbh" in blob:
        return "GmbH"
    if re.search(r"\bug\b|haftungsbeschr", blob):
        return "UG"
    if re.search(r"\bgbr\b", blob):
        return "GbR"
    if re.search(r"\be\.?\s?k\.?\b", blob):
        return "e.K."
    return None


def find_team_url(homepage_html: str, base_url: str) -> str | None:
    soup = BeautifulSoup(homepage_html, "lxml")
    best = None
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(" ", strip=True).lower()
        blob = (href + " " + text).lower()
        if any(h in blob for h in ("team", "mitarbeiter", "das-team", "unser team", "über uns", "ueber-uns", "über-uns")):
            url = urljoin(base_url, href)
            if "team" in blob or "mitarbeiter" in blob:
                return url  # stärkster Treffer
            best = best or url
    return best


def count_team_members(html: str) -> int:
    """Distinkte Personen auf einer Team-Seite (Name in Nähe eines Rollen-Stichworts)."""
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text("  ", strip=True)
    names: set[str] = set()
    for m in _ROLE.finditer(text):
        window = text[max(0, m.start() - 45): m.end() + 45]
        for nm in _NAME.finditer(window):
            cand = nm.group(0).strip()
            # Rollenwörter selbst nicht als Name zählen
            if _ROLE.fullmatch(cand) or len(cand) < 3:
                continue
            names.add(cand.lower())
    if names:
        return len(names)
    # Fallback: rohe Rollen-Treffer (schwächeres Signal)
    return len(_ROLE.findall(text))


def _bucket(n: int) -> str:
    if n <= 2:
        return "1-2"
    if n <= 5:
        return "3-5"
    if n <= 10:
        return "6-10"
    return "11+"


def estimate_size(
    client: HttpClient,
    name: str,
    homepage_url: str | None,
    homepage_html: str | None,
    impressum_text: str,
    owner: str | None,
) -> dict:
    """Liefert {estimate, confidence, basis}."""
    legal = detect_legal_form(name, impressum_text)

    # 1) Team-Seite auswerten
    if homepage_html and homepage_url:
        team_url = find_team_url(homepage_html, homepage_url)
        if team_url:
            resp = client.get(team_url)
            if resp.ok and resp.text:
                count = count_team_members(resp.text)
                if count >= 1:
                    conf = "hoch" if count >= 3 else "mittel"
                    return {
                        "estimate": _bucket(count),
                        "confidence": conf,
                        "basis": f"Team-Seite: ~{count} Personen genannt ({urlparse(team_url).path})",
                    }

    # 2) Mehrere Geschäftsführer im Impressum
    gf_names = re.findall(r"Gesch[äa]ftsf[üu]hrer(?:in)?\s*[:\-]?\s*([A-ZÄÖÜ][^\n,;]{2,60})", impressum_text)
    if len(gf_names) >= 2:
        return {"estimate": "3-5", "confidence": "niedrig", "basis": "mehrere Geschäftsführer im Impressum"}

    # 3) Rechtsform als schwaches Signal
    if legal in ("GmbH", "AG"):
        return {"estimate": "3-5", "confidence": "niedrig", "basis": f"Rechtsform {legal} (deutet auf größeren Betrieb)"}

    return {"estimate": "unbekannt", "confidence": "niedrig", "basis": "keine belastbaren Signale gefunden"}
