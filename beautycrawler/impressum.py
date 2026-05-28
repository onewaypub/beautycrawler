"""Impressum lokalisieren und Pflichtfelder extrahieren.

Extrahiert: Geschäftsführer/Inhaber, Adresse, E-Mail, Fax, USt-IdNr.
Heuristisch und fehlertolerant — fehlende Felder bleiben None.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .http_client import HttpClient, Response

IMPRESSUM_PATHS = [
    "impressum", "impressum/", "impressum.html", "impressum.php", "impressum.htm",
    "de/impressum", "impressum-datenschutz", "imprint", "kontakt/impressum",
    "ueber-uns/impressum", "rechtliches/impressum", "impressum-kontakt",
]

# Inter-Wort-Trenner bewusst OHNE \n (nur Space/Tab/Nbsp/Bindestrich), damit der
# Name nicht in die nächste Zeile (z. B. die Straße) ausläuft.
_NAME = (
    r"(?:Dr\.[ \t]*|Prof\.[ \t]*|Dipl\.[-\w]*[ \t]*|Herrn?[ \t]+|Frau[ \t]+)*"
    r"[A-ZÄÖÜ][a-zäöüß]+(?:[-  \t]+(?:[A-ZÄÖÜ]\.|[A-ZÄÖÜ][a-zäöüß]+)){1,3}"
)

# Owner-Muster in Prioritätsreihenfolge. \b verhindert Treffer mitten im Wort;
# der Name muss direkt (max. kurze Zwischenfloskel) hinter dem Label stehen.
_OWNER_PATTERNS = [
    # Label vor dem Namen
    re.compile(rf"\b(?:Gesch[äa]ftsf[üu]hrer(?:in)?|Inhaber(?:in)?|Inh\.)\b\s*[:\-]?\s*(?:ist\s+|Herrn?\s+|Frau\s+)?({_NAME})", re.IGNORECASE),
    re.compile(rf"\bvertreten durch\b\s*(?:den|die|Herrn?|Frau|Gesch[äa]ftsf[üu]hrer(?:in)?)?\s*[:\-]?\s*({_NAME})", re.IGNORECASE),
    re.compile(rf"\bVertretungsberechtigte[rs]?\b[^:\n]{{0,25}}[:\-]\s*({_NAME})", re.IGNORECASE),
    # Name vor dem Label, z. B. "Max Mustermann (Inhaber)" / "… - Inhaberin"
    # Klammer/Bindestrich PFLICHT, sonst würde "Salon Schmidt Inhaber" falsch greifen.
    re.compile(rf"({_NAME})\s*[\(\-–]\s*(?:Inhaber(?:in)?|Gesch[äa]ftsf[üu]hrer(?:in)?)\b", re.IGNORECASE),
    # Verantwortlich i.S.d. § 18 MStV / § 55 RStV (häufig der Inhaber bei Kleinbetrieben)
    re.compile(rf"§\s*(?:18|55)[^:\n]{{0,45}}(?:MStV|RStV)[^:\n]{{0,45}}[:\-]?\s*({_NAME})", re.IGNORECASE),
    re.compile(rf"\bVerantwortlich(?:e[rs])?\s+f[üu]r\s+den\s+Inhalt[^:\n]{{0,50}}[:\-]?\s*({_NAME})", re.IGNORECASE),
]

_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_FAX = re.compile(r"(?:Fax|Telefax)[^\d+]{0,12}([+()\d][\d\s/().\-]{5,})", re.IGNORECASE)
_VAT = re.compile(r"\bDE\s?\d{9}\b")
_PLZ_CITY_LINE = re.compile(r"^\s*(?:D[-\s])?(\d{5})\s+([A-ZÄÖÜ][A-Za-zäöüß.\-/ ]{2,40})\s*$")
_PLZ_CITY_INLINE = re.compile(r"\b(?:D[-\s])?(\d{5})\s+([A-ZÄÖÜ][A-Za-zäöüß.\-]{2,40})")
_BAD_STREET_LINE = re.compile(r"@|tel\.?|fon|fax|mail|ust|steuer|http|www\.", re.IGNORECASE)


def _looks_like_street(s: str) -> bool:
    return bool(
        4 <= len(s) <= 60
        and not _BAD_STREET_LINE.search(s)
        and re.search(r"[A-Za-zäöüß]{3,}", s)
        and re.search(r"\d+\s*[a-zA-Z]?\s*$", s)  # endet auf Hausnummer
    )


def _extract_address(text: str) -> str | None:
    """Adresse zeilenbasiert: PLZ+Ort suchen, Straße = Zeile davor oder gleiche Zeile."""
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    for i, line in enumerate(lines):
        mline = _PLZ_CITY_LINE.match(line)
        minline = None if mline else _PLZ_CITY_INLINE.search(line)
        m = mline or minline
        if not m:
            continue
        plz, city = m.group(1), m.group(2).strip(" .,-")
        # Straße auf gleicher Zeile (vor der PLZ)?
        if minline:
            prefix = line[: minline.start()].strip(" ,;·|-")
            if prefix and _looks_like_street(prefix):
                return f"{prefix}, {plz} {city}"
        # sonst Zeile(n) darüber
        for j in (i - 1, i - 2):
            if j >= 0 and _looks_like_street(lines[j]):
                return f"{lines[j]}, {plz} {city}"
        return f"{plz} {city}"
    return None


def _deobfuscate_email(text: str) -> str:
    t = text
    t = re.sub(r"\s*\(\s*at\s*\)\s*|\s*\[\s*at\s*\]\s*|\s+at\s+|\s*\{\s*at\s*\}\s*", "@", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*\(\s*(?:dot|punkt)\s*\)\s*|\s*\[\s*(?:dot|punkt)\s*\]\s*|\s+(?:dot|punkt)\s+", ".", t, flags=re.IGNORECASE)
    return t


def find_impressum_url(client: HttpClient, homepage_url: str) -> tuple[str | None, Response | None]:
    """Liefert (impressum_url | None, homepage_response). homepage_response für Status/Reuse."""
    home = client.get(homepage_url)
    if not home.ok or not home.text:
        # Bei tiefem Pfad die Root-Domain probieren (Quellen verlinken oft Unterseiten).
        parsed = urlparse(homepage_url)
        if parsed.path not in ("", "/") or parsed.query:
            root = f"{parsed.scheme}://{parsed.netloc}/"
            alt = client.get(root)
            if alt.ok and alt.text:
                home, homepage_url = alt, root
    if not home.ok or not home.text:
        return None, home

    soup = BeautifulSoup(home.text, "lxml")
    base = home.url or homepage_url
    candidates: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(" ", strip=True).lower()
        if "impressum" in href.lower() or "imprint" in href.lower() or "impressum" in text or "imprint" in text:
            candidates.append(urljoin(base, href))
    # eindeutige, sinnvolle Reihenfolge
    seen = set()
    for c in candidates:
        if c not in seen:
            seen.add(c)
            return c, home

    # Fallback: typische Pfade probieren
    root = f"{urlparse(base).scheme}://{urlparse(base).netloc}/"
    for path in IMPRESSUM_PATHS:
        url = urljoin(root, path)
        resp = client.get(url)
        if resp.ok and resp.text and ("impressum" in resp.text.lower() or "umsatzsteuer" in resp.text.lower()):
            return url, home
    return None, home


def extract_fields(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")

    # mailto bevorzugt (zuverlässigste E-Mail-Quelle)
    email = None
    for a in soup.find_all("a", href=True):
        if a["href"].lower().startswith("mailto:"):
            cand = a["href"][7:].split("?")[0].strip()
            if _EMAIL.fullmatch(cand):
                email = cand
                break

    text = soup.get_text("\n", strip=True)

    if not email:
        m = _EMAIL.search(_deobfuscate_email(text))
        if m:
            email = m.group(0)

    owner = None
    for pat in _OWNER_PATTERNS:
        mo = pat.search(text)
        if mo:
            cand = re.sub(r"\s+", " ", mo.group(1)).strip(" .,-")
            if len(cand) >= 5:
                owner = cand
                break

    fax = None
    mf = _FAX.search(text)
    if mf:
        fax = re.sub(r"\s+", " ", mf.group(1)).strip(" .,-")

    vat = None
    mv = _VAT.search(text)
    if mv:
        vat = re.sub(r"\s+", "", mv.group(0))

    address = _extract_address(text)

    return {"owner": owner, "email": email, "fax": fax, "vat_id": vat, "impressum_address": address}
