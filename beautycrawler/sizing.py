"""Firmengröße schätzen — konservativ, mit Konfidenz und nachvollziehbarer Basis.

Zuverlässige Mitarbeiterzahlen von Websites sind kaum erreichbar; daher:
- Team-Seite STRUKTURELL auswerten (Personennamen nur aus Überschriften/Bild-alt/
  Namens-Elementen, nicht aus Fließtext) und deckeln → keine absurden Zahlen mehr.
- Positive ">=3"-Signale: mehrere Geschäftsführer, Stellenangebote/Karriere.
- Einzelbetrieb-Signale für "1-2" (nur dann greift der <3-Filter, und auch nur bei
  ausreichender Konfidenz — siehe pipeline).
Buckets: 1-2, 3-5, 6-10, 11+, unbekannt.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .http_client import HttpClient

# Ein Personenname: 2-3 großgeschriebene Tokens (Vor- + Nachname[n]).
_PERSON = re.compile(r"[A-ZÄÖÜ][a-zäöüß]+(?:[ -][A-ZÄÖÜ][a-zäöüß]+){1,2}")
_ROLE = re.compile(
    r"\b(?:Friseur(?:in|meister(?:in)?)?|Stylist(?:in)?|Colorist(?:in)?|Barber|"
    r"Kosmetiker(?:in)?|Nageldesigner(?:in)?|Masseur(?:in)?|Visagist(?:in)?|"
    r"Heilpraktiker(?:in)?|Inhaber(?:in)?|Gesch[äa]ftsf[üu]hrer(?:in)?|"
    r"Auszubildende[rs]?|Azubi|Meister(?:in)?)\b",
    re.IGNORECASE,
)

# Tokens, die ein "Name"-Kandidat NICHT enthalten darf (sonst ist es kein Personenname).
_NOT_NAME = {
    "unser", "unsere", "unseren", "über", "ueber", "team", "salon", "studio",
    "friseur", "kosmetik", "beauty", "hair", "haar", "kontakt", "impressum",
    "leistungen", "preise", "preisliste", "öffnungszeiten", "oeffnungszeiten",
    "aktuelles", "news", "galerie", "termin", "termine", "willkommen", "herzlich",
    "jetzt", "mehr", "start", "home", "datenschutz", "anfahrt", "gutschein",
    "gutscheine", "karriere", "jobs", "stellenangebote", "bewertungen",
    "philosophie", "produkte", "cookie", "cookies", "facebook", "instagram",
    "montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag",
    "sonntag", "ihr", "ihre", "wir", "sie", "neu", "the", "and", "for", "your",
}

_HIRING = re.compile(
    r"stellenangebot|wir suchen|karriere|ausbildungsplatz|azubi|verst[äa]rkung|"
    r"bewerb|quereinsteiger|jetzt bewerben|mitarbeiter\s*\(|m/w/d|w/m/d",
    re.IGNORECASE,
)


def detect_legal_form(name: str, impressum_text: str) -> str | None:
    blob = f"{name} {impressum_text}".lower()
    if "gmbh" in blob:
        return "GmbH"
    if re.search(r"\bag\b", blob):
        return "AG"
    if re.search(r"\bug\b|haftungsbeschr", blob):
        return "UG"
    if re.search(r"\bgbr\b", blob):
        return "GbR"
    if re.search(r"\be\.?\s?k\.?\b", blob):
        return "e.K."
    return None


def count_managing_directors(impressum_text: str) -> int:
    """Anzahl genannter Geschäftsführer/Inhaber (über Komma/und/&-Trennung)."""
    m = re.search(
        r"(?:Gesch[äa]ftsf[üu]hrer(?:in)?|Inhaber(?:in)?|vertreten durch)\s*[:\-]?\s*([^\n]{3,120})",
        impressum_text, re.IGNORECASE,
    )
    if not m:
        return 0
    tail = re.split(r"\b(?:USt|Umsatzsteuer|Tel|Telefon|E-?Mail|Registergericht|HRB)\b", m.group(1))[0]
    names = _PERSON.findall(tail)
    names = [n for n in names if not any(t.lower() in _NOT_NAME for t in n.split())]
    return len(set(names))


def find_team_url(homepage_html: str, base_url: str) -> str | None:
    soup = BeautifulSoup(homepage_html, "lxml")
    best = None
    for a in soup.find_all("a", href=True):
        blob = (a["href"] + " " + a.get_text(" ", strip=True)).lower()
        if any(h in blob for h in ("team", "mitarbeiter", "unser team", "über uns", "ueber-uns", "über-uns", "das-team")):
            url = urljoin(base_url, a["href"])
            if "team" in blob or "mitarbeiter" in blob:
                return url
            best = best or url
    return best


def _is_person_name(text: str) -> bool:
    t = text.strip()
    if not (4 <= len(t) <= 40):
        return False
    m = _PERSON.match(t)
    if not m:
        return False
    name = m.group(0)
    toks = name.split()
    if any(tok.lower() in _NOT_NAME for tok in toks):
        return False
    if _ROLE.search(name):
        return False
    return True


def count_team_members(html: str) -> int:
    """Distinkte Personennamen aus STRUKTUR-Elementen (Überschriften/alt/Namens-Klassen)."""
    soup = BeautifulSoup(html, "lxml")
    candidates: list[str] = []
    for tag in soup.find_all(["h2", "h3", "h4", "h5", "figcaption", "strong", "b"]):
        candidates.append(tag.get_text(" ", strip=True))
    for img in soup.find_all("img"):
        if img.get("alt"):
            candidates.append(img["alt"].strip())
    for el in soup.select('[class*="name" i], [class*="member" i], [class*="mitarbeiter" i], [class*="team" i]'):
        txt = el.get_text(" ", strip=True)
        if len(txt) <= 40:
            candidates.append(txt)

    names: set[str] = set()
    for c in candidates:
        if _is_person_name(c):
            names.add(_PERSON.match(c).group(0).lower())
    return len(names)


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
    """Liefert {estimate, confidence, basis}. Konservativ: lieber 'unbekannt' als falsch."""
    home_text = ""
    if homepage_html:
        home_text = BeautifulSoup(homepage_html, "lxml").get_text(" ", strip=True)
    legal = detect_legal_form(name, impressum_text)
    n_gf = count_managing_directors(impressum_text)

    # 1) Team-Seite strukturell auswerten
    team_url = find_team_url(homepage_html, homepage_url) if (homepage_html and homepage_url) else None
    team_count = 0
    if team_url:
        resp = client.get(team_url)
        if resp.ok and resp.text:
            team_count = count_team_members(resp.text)
    path = urlparse(team_url).path if team_url else ""

    # Nur >=3 gilt als sicheres Mehrpersonen-Signal. 1-2 gezählte Namen sind
    # mehrdeutig (evtl. unvollständige/falsche Seite, z. B. nur die Inhaber) ->
    # NICHT als 'klein' werten, sondern unten weiterprüfen.
    if 3 <= team_count <= 20:
        return {"estimate": _bucket(team_count), "confidence": "hoch",
                "basis": f"Team-Seite: {team_count} Personennamen ({path})"}
    if team_count > 20:
        # unplausibel viele -> wahrscheinlich Seiteninhalt, nicht Personal
        return {"estimate": "11+", "confidence": "niedrig",
                "basis": f"Team-Seite: {team_count} Namen (unsicher, evtl. Seiteninhalt)"}

    # 2) Positive >=3-Signale
    if n_gf >= 2:
        return {"estimate": "3-5", "confidence": "mittel",
                "basis": f"{n_gf} Geschäftsführer/Inhaber im Impressum"}
    if home_text and _HIRING.search(home_text):
        return {"estimate": "3-5", "confidence": "niedrig",
                "basis": "Stellenangebote/Karriere → mehrere Mitarbeiter"}

    # 3) Einzelbetrieb-Signale (für den <3-Filter)
    has_team_mention = bool(re.search(r"\b(unser\s+team|das\s+team|mitarbeiter)\b", home_text, re.IGNORECASE))
    solo_language = bool(re.search(r"\b(mein\s+salon|bei\s+mir|ich\s+freue\s+mich|ich\s+biete|als\s+inhaberin|als\s+inhaber)\b", home_text, re.IGNORECASE))
    if not team_url and not has_team_mention and legal in (None, "e.K.") and n_gf <= 1:
        if solo_language:
            return {"estimate": "1-2", "confidence": "mittel",
                    "basis": "Einzelbetrieb-Sprache, kein Team genannt"}
        return {"estimate": "1-2", "confidence": "niedrig",
                "basis": "kein Team/keine Mitarbeiter erkennbar (unsicher)"}

    # 4) Rechtsform als schwaches Signal
    if legal in ("GmbH", "AG"):
        return {"estimate": "3-5", "confidence": "niedrig",
                "basis": f"Rechtsform {legal} (deutet auf größeren Betrieb)"}

    return {"estimate": "unbekannt", "confidence": "niedrig", "basis": "keine belastbaren Signale"}
