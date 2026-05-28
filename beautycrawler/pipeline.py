"""Orchestrierung: Discovery -> Dedupe -> Website -> Impressum -> Größe -> Filter -> CSV."""
from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from pathlib import Path

from bs4 import BeautifulSoup

from . import impressum as imp
from . import sizing
from .http_client import HttpClient
from .models import CSV_FIELDS, Business
from .sources.base import Area, Source
from .websearch import resolve_website, website_from_detail_page

log = logging.getLogger("beautycrawler.pipeline")


@dataclass
class Metrics:
    discovered_total: int = 0
    per_source: dict = field(default_factory=dict)
    after_dedupe: int = 0
    duplicates: int = 0
    with_website_source: int = 0
    website_resolved: int = 0
    without_website: int = 0
    processed: int = 0
    website_ok: int = 0
    website_dead: int = 0
    impressum_found: int = 0
    filled_email: int = 0
    filled_owner: int = 0
    filled_fax: int = 0
    filled_vat: int = 0
    filled_address: int = 0
    size_dist: dict = field(default_factory=dict)
    dropped_small: int = 0
    final_count: int = 0
    errors: int = 0

    def report(self) -> str:
        def pct(n, d):
            return f"{(100 * n / d):.0f}%" if d else "—"

        lines = [
            "================ METRIKEN ================",
            f"Discovery gesamt (vor Dedupe): {self.discovered_total}",
        ]
        for s, c in self.per_source.items():
            lines.append(f"   - {s}: {c}")
        lines += [
            f"Nach Dedupe: {self.after_dedupe} ({self.duplicates} Duplikate zusammengeführt)",
            f"Website aus Quelle: {self.with_website_source} | per Suche aufgelöst: {self.website_resolved} | ohne Website (verworfen): {self.without_website}",
            f"Verarbeitet (Homepage abgerufen): {self.processed}",
            f"   Website erreichbar: {self.website_ok} | tot/blockiert: {self.website_dead}",
            f"   Impressum gefunden: {self.impressum_found} ({pct(self.impressum_found, self.website_ok)} der erreichbaren)",
            "Feldabdeckung (von erreichbaren Websites):",
            f"   E-Mail:   {self.filled_email} ({pct(self.filled_email, self.website_ok)})",
            f"   Inhaber:  {self.filled_owner} ({pct(self.filled_owner, self.website_ok)})",
            f"   Adresse:  {self.filled_address} ({pct(self.filled_address, self.website_ok)})",
            f"   USt-IdNr: {self.filled_vat} ({pct(self.filled_vat, self.website_ok)})",
            f"   Fax:      {self.filled_fax} ({pct(self.filled_fax, self.website_ok)})",
            f"Größenverteilung: {dict(self.size_dist)}",
            f"Verworfen (<3 Personen geschätzt): {self.dropped_small}",
            f"Fehler: {self.errors}",
            f">>> FINALE DATENSÄTZE: {self.final_count} <<<",
            "==========================================",
        ]
        return "\n".join(lines)


def _dedupe(businesses: list[Business]) -> list[Business]:
    merged: dict[str, Business] = {}
    for b in businesses:
        key = b.dedupe_key()
        if key in merged:
            merged[key].merge(b)
        else:
            merged[key] = b
    return list(merged.values())


def _short(s: str, n: int = 42) -> str:
    s = s or ""
    return s if len(s) <= n else s[: n - 1] + "…"


def _yn(v) -> str:
    return "ja" if v else "—"


def run(
    sources: list[Source],
    area: Area,
    client: HttpClient,
    *,
    limit: int | None = None,
    min_size: int = 3,
    resolve_missing: bool = True,
    use_ddg: bool = False,
    out_path: str = "output/salons.csv",
) -> Metrics:
    m = Metrics()
    cap = limit or 0

    # 1) DISCOVERY
    log.info("─── SCHRITT 1: DISCOVERY (Gebiet: %s) ───", area.name)
    all_biz: list[Business] = []
    for src in sources:
        try:
            found = src.discover(client, area)
            n_web = sum(1 for x in found if x.website)
            m.per_source[src.name] = len(found)
            all_biz.extend(found)
            log.info("  Quelle %-7s: %4d Treffer (davon mit Website: %d)", src.name, len(found), n_web)
        except Exception as e:  # eine kaputte Quelle darf den Lauf nicht stoppen
            m.errors += 1
            m.per_source[src.name] = 0
            log.warning("  Quelle %-7s FEHLER: %s", src.name, e)
    m.discovered_total = len(all_biz)

    # 2) DEDUPE
    deduped = _dedupe(all_biz)
    m.after_dedupe = len(deduped)
    m.duplicates = m.discovered_total - m.after_dedupe
    log.info("─── SCHRITT 2: DEDUPE: %d → %d (%d Duplikate) ───", m.discovered_total, m.after_dedupe, m.duplicates)

    # 3) Reihenfolge: Einträge mit Website zuerst, dann die ohne (lazy aufgelöst).
    m.with_website_source = sum(1 for b in deduped if b.website)
    ordered = [b for b in deduped if b.website] + [b for b in deduped if not b.website]
    log.info(
        "─── SCHRITT 3-7: VERARBEITUNG (max %s Firmen; %d mit Website, %d ohne) ───",
        cap or "∞", m.with_website_source, m.after_dedupe - m.with_website_source,
    )

    kept: list[Business] = []
    for b in ordered:
        if cap and m.processed >= cap:
            log.info("  Limit von %d verarbeiteten Firmen erreicht — stoppe.", cap)
            break

        # 3a) Website ggf. auflösen: zuerst Verzeichnis-Detailseite, dann optional DDG
        origin = "Quelle"
        if not b.website:
            if not resolve_missing:
                continue
            site = None
            if b.detail_url:
                try:
                    site = website_from_detail_page(client, b.detail_url)
                    if site:
                        origin = "Detailseite"
                except Exception:
                    m.errors += 1
            if not site and use_ddg:
                try:
                    site = resolve_website(client, b.name, b.city, b.postcode)
                    if site:
                        origin = "Suche"
                except Exception:
                    m.errors += 1
            if site:
                b.website = site
                m.website_resolved += 1
            else:
                m.without_website += 1
                log.info("  [—]    %-42s | keine Website gefunden → übersprungen", _short(b.name))
                continue

        n = m.processed + 1
        m.processed += 1
        log.info("  [%2d/%s] %-42s | %s | Website (%s): %s",
                 n, cap or "∞", _short(b.name), "/".join(b.categories) or "?", origin, b.website)

        # 4) Homepage + Impressum
        try:
            impressum_url, home = imp.find_impressum_url(client, b.website)
        except Exception as e:
            m.errors += 1
            home, impressum_url = None, None
            log.debug("      Fehler beim Homepage-Abruf: %s", e)

        if not home or not home.ok or not home.text:
            b.website_status = "dead"
            m.website_dead += 1
            status = home.status if home else "—"
            log.info("      Homepage nicht erreichbar (Status %s) → übersprungen", status)
            continue
        b.website_status = "ok"
        m.website_ok += 1

        # 5) Felder aus Impressum
        impressum_text = ""
        if impressum_url:
            try:
                ir = client.get(impressum_url)
                if ir.ok and ir.text:
                    b.impressum_url = impressum_url
                    m.impressum_found += 1
                    fields = imp.extract_fields(ir.text)
                    impressum_text = BeautifulSoup(ir.text, "lxml").get_text("\n", strip=True)
                    for k, v in fields.items():
                        if v and not getattr(b, k, None):
                            setattr(b, k, v)
                    log.info("      Impressum: %s", impressum_url)
            except Exception:
                m.errors += 1
        if not b.impressum_url:
            log.info("      Impressum: nicht gefunden")
        log.info("      Felder → E-Mail=%s  Inhaber=%s  Fax=%s  USt=%s  Adresse=%s",
                 _yn(b.email), _short(b.owner or "—", 24), _yn(b.fax), _yn(b.vat_id), _yn(b.impressum_address))

        # 6) Größenschätzung
        try:
            size = sizing.estimate_size(client, b.name, b.website, home.text, impressum_text, b.owner)
            b.size_estimate, b.size_confidence, b.size_basis = size["estimate"], size["confidence"], size["basis"]
        except Exception:
            m.errors += 1
            b.size_estimate, b.size_confidence, b.size_basis = "unbekannt", "niedrig", "Schätzung fehlgeschlagen"
        log.info("      Größe: %s (Konfidenz %s) — %s", b.size_estimate, b.size_confidence, b.size_basis)

        if b.email:
            m.filled_email += 1
        if b.owner:
            m.filled_owner += 1
        if b.fax:
            m.filled_fax += 1
        if b.vat_id:
            m.filled_vat += 1
        if b.impressum_address:
            m.filled_address += 1
        m.size_dist[b.size_estimate] = m.size_dist.get(b.size_estimate, 0) + 1

        # 7) Größenfilter (<3): nur verwerfen, wenn klar 1-2
        if b.size_estimate == "1-2":
            m.dropped_small += 1
            log.info("      → VERWORFEN (geschätzt <3 Personen)")
            continue
        kept.append(b)
        log.info("      → BEHALTEN")

    # 8) OUTPUT
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, delimiter=";")
        w.writeheader()
        for b in kept:
            w.writerow(b.to_csv_row())
    m.final_count = len(kept)
    log.info("─── SCHRITT 8: %d Datensätze geschrieben → %s ───", m.final_count, out)
    return m
