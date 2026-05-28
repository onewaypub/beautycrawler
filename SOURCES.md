# Quellen-Katalog (Stand 2026-05-28)

Alle Quellen sind kostenlos. robots.txt wurde geprüft; gesperrte Quellen werden
respektiert und ausgeschlossen. Faires Crawling (eindeutiger User-Agent,
Rate-Limits, Caching) ist Standard.

## Status-Legende
- **aktiv** = implementiert und im Einsatz
- **geplant** = validiert (robots/Erreichbarkeit), Integration folgt in späterer Iteration
- **gesperrt** = per robots.txt untersagt → ausgeschlossen

## Strukturierte Quellen (Website oft direkt enthalten)
| Quelle | Status | robots | Hinweis |
|---|---|---|---|
| OpenStreetMap / Overpass API | **aktiv** | API (ODbL) | Name/Adresse/Website/Branche; lückenhaft außerhalb von Großstädten |
| 11880.com | **aktiv** | erlaubt (Suche frei) | Listing als JSON-LD (50/Seite); eigene Website per Suche aufgelöst |
| Das Örtliche (dasoertliche.de) | **aktiv** | `Disallow:` leer = alles erlaubt | Listing-JSON-LD (/Themen/<Branche>/<Stadt>.html); Website via Detailseite |
| GoYellow (goyellow.de) | **aktiv** | `/suche/` erlaubt (außer Filter-Params) | Listing als Microdata (LocalBusiness); Website via Detailseite |
| meinestadt.de | verworfen | robots ok, aber Server blockt Bot-UA (HTTP 403) | nur mit Browser-UA scrapebar → aus Fairness verworfen |
| stadtbranchenbuch.com | **aktiv** | `/search` gesperrt, Kategorieseiten erlaubt | City-Subdomains; **Website direkt inline** im Listing; Name/Adresse via JSON-LD |

## Via Sitemaps (gut für deutschlandweit)
| Quelle | Status | Hinweis |
|---|---|---|
| Gelbe Seiten | zurückgestellt | Sitemaps orts-orientiert (Bundesland/Landkreis), NICHT branchen-filterbar → nur per Massen-Crawl |
| branchenbuchdeutschland.de | geplant | Sitemaps pro Bundesland (sitemap_by.xml = Bayern …) |

## Buchungsplattformen (eigene Website meist NICHT verlinkt → Auflösung nötig)
| Quelle | Status | robots |
|---|---|---|
| Treatwell (treatwell.de) | geplant | crawlbar, Crawl-delay 5 |
| Planity (planity.com) | geplant | Business-Seiten erlaubt |

## Open-Data-Datensätze (license-clean, hohe Abdeckung, für Skalierung)
| Quelle | Status | Hinweis |
|---|---|---|
| Overture Maps Places | geplant | offen; per DuckDB auf Remote-Parquet mit bbox/Kategorie filtern |
| Foursquare OS Places | geplant | offener Places-Datensatz mit Website/Kategorie |

## Anreicherung
| Quelle | Status | Hinweis |
|---|---|---|
| DuckDuckGo HTML-Endpoint | **aktiv** | löst fehlende eigene Websites auf; Aggregatoren/Social gefiltert |

## Gesperrt (respektiert, ausgeschlossen)
- **yelp.de** — `Disallow: /`
- **booksy.com** — `Disallow: /`

## Branchen / OSM-Tags
Friseur (`shop=hairdresser`, `craft=hairdresser`), Kosmetik (`shop=beauty`),
Maniküre/Nagel (`beauty=nails`), Pediküre/Fußpflege (`beauty=pedicure`),
Massage (`shop=massage`), Visagistik (`beauty=make_up`).
