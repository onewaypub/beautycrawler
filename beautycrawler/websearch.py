"""Website-Auflösung per DuckDuckGo-HTML-Endpoint.

Für Firmen ohne bekannte eigene Website (z. B. aus Verzeichnissen/Buchungs-
plattformen) versuchen wir, die offizielle Domain über eine Suchanfrage zu finden.
Aggregatoren/Social-Media werden gefiltert, damit nicht ein Verzeichnis-Link als
'Website' durchrutscht.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urlparse

from .http_client import HttpClient
from .models import normalize_name

DDG_HTML = "https://html.duckduckgo.com/html/"

# Domains, die NIE als 'eigene Website' eines Salons zählen.
BLOCKLIST = {
    "11880.com", "dasoertliche.de", "gelbeseiten.de", "goyellow.de", "yelp.de",
    "yelp.com", "treatwell.de", "planity.com", "booksy.com", "meinestadt.de",
    "golocal.de", "cylex.de", "stadtbranchenbuch.com", "branchenbuchdeutschland.de",
    "facebook.com", "instagram.com", "tiktok.com", "youtube.com", "twitter.com",
    "x.com", "linkedin.com", "pinterest.de", "pinterest.com", "wikipedia.org",
    "google.com", "google.de", "maps.google.com", "tripadvisor.de", "jameda.de",
    "kununu.com", "indeed.com", "wer-kennt-den-besten.de", "werkenntdenbesten.de",
    "provenexpert.com", "fnp.de", "11880-friseur.com", "salon-zauber.de",
    # Rauschen auf 11880-Detailseiten
    "wirfindendeinenjob.de", "cleverb2b.de", "postleitzahlen.de", "bundesnetzagentur.de",
    "powerappsportals.com", "ekomi.de", "localytix.de", "microsoft.com", "bing.com",
    "apple.com", "whatsapp.com", "t.me", "wa.me", "goo.gl", "bit.ly",
}


def _registrable(host: str) -> str:
    host = host.lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host


def _is_blocked(host: str) -> bool:
    host = _registrable(host)
    if not host or "." not in host:
        return True
    return any(host == b or host.endswith("." + b) for b in BLOCKLIST)


_WEBSITE_LABELS = ("zur webseite", "zur website", "webseite", "website", "homepage", "zur homepage", "internet")


def website_from_detail_page(client: HttpClient, detail_url: str) -> str | None:
    """Echte Firmen-Website aus einer Verzeichnis-Detailseite (z. B. 11880) extrahieren.

    Zuerst ein als 'Website/Webseite' beschrifteter Link; sonst die am häufigsten
    verlinkte externe Nicht-Aggregator-Domain.
    """
    resp = client.get(detail_url)
    if not resp.ok or not resp.text:
        return None

    from collections import Counter

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(resp.text, "lxml")

    # 1) beschrifteter Website-Link
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href.startswith("http"):
            continue
        host = urlparse(href).netloc
        if _is_blocked(host):
            continue
        text = a.get_text(" ", strip=True).lower()
        if any(lbl in text for lbl in _WEBSITE_LABELS):
            return f"https://{_registrable(host)}/"

    # 2) häufigste externe Domain als Fallback
    counts: Counter = Counter()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href.startswith("http"):
            continue
        host = _registrable(urlparse(href).netloc)
        if _is_blocked(host):
            continue
        counts[host] += 1
    if counts:
        return f"https://{counts.most_common(1)[0][0]}/"
    return None


def _extract_real_url(href: str) -> str | None:
    """Aus DDG-Redirect (//duckduckgo.com/l/?uddg=...) die echte URL ziehen."""
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l"):
        qs = parse_qs(parsed.query)
        if "uddg" in qs:
            return unquote(qs["uddg"][0])
        return None
    if parsed.scheme in ("http", "https"):
        return href
    return None


def _name_matches(business_name: str, title: str, host: str) -> bool:
    """Heuristik: mind. ein aussagekräftiges Namens-Token in Titel oder Domain."""
    tokens = [t for t in normalize_name(business_name).split() if len(t) >= 4]
    if not tokens:
        tokens = [t for t in normalize_name(business_name).split() if len(t) >= 3]
    if not tokens:
        return False
    hay = (title + " " + host).lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    return any(t in hay for t in tokens)


def resolve_website(client: HttpClient, name: str, city: str | None, postcode: str | None = None) -> str | None:
    parts = [name]
    if city:
        parts.append(city)
    query = " ".join(parts)
    resp = client.get(
        DDG_HTML, method="POST", data={"q": query, "kl": "de-de"},
        respect_robots=False, use_cache=True,
    )
    if not resp.ok:
        return None

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(resp.text, "lxml")
    for a in soup.select("a.result__a"):
        href = a.get("href", "")
        title = a.get_text(" ", strip=True)
        real = _extract_real_url(href)
        if not real:
            continue
        host = _registrable(urlparse(real).netloc)
        if not host or "." not in host:
            continue
        if any(host == b or host.endswith("." + b) for b in BLOCKLIST):
            continue
        if not _name_matches(name, title, host):
            continue
        return f"{urlparse(real).scheme}://{host}/"
    return None
