"""HTTP-Client: eindeutiger User-Agent, robots.txt, Rate-Limit, Retries, Disk-Cache."""
from __future__ import annotations

import hashlib
import json
import time
import urllib.robotparser
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests
import urllib3

# Kleinbetriebe haben oft fehlerhafte Zertifikate; bei SSL-Fehler fällt get() auf
# verify=False zurück. Die zugehörige Warnung unterdrücken.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# WICHTIG: kein "Mozilla/..."-Prefix! Die Overpass-API liefert für browser-artige
# User-Agents 406 Not Acceptable. Ein ehrlicher Bot-UA wird von Overpass UND den
# Verzeichnissen/Salon-Seiten akzeptiert (getestet) und entspricht der Fairness-Vorgabe.
DEFAULT_UA = "beautycrawler/0.1 (+https://github.com/onewaypub/beautycrawler)"


@dataclass
class Response:
    url: str
    status: int
    text: str
    ok: bool
    from_cache: bool = False
    error: str | None = None


class HttpClient:
    def __init__(
        self,
        user_agent: str = DEFAULT_UA,
        cache_dir: str | Path = ".cache",
        default_delay: float = 1.5,
        timeout: float = 15.0,
        max_retries: int = 2,
        respect_robots: bool = True,
        cache_ttl_days: float = 14.0,
    ):
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_retries = max_retries
        self.default_delay = default_delay
        self.respect_robots = respect_robots
        self.cache_ttl = cache_ttl_days * 86400
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent, "Accept-Language": "de-DE,de;q=0.9"})
        self._last_host_access: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._crawl_delay: dict[str, float] = {}

    # ---- Cache ---------------------------------------------------------------
    def _cache_path(self, key: str) -> Path:
        h = hashlib.sha1(key.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{h}.json"

    def _cache_read(self, key: str) -> Response | None:
        p = self._cache_path(key)
        if not p.exists():
            return None
        try:
            if self.cache_ttl and (time.time() - p.stat().st_mtime) > self.cache_ttl:
                return None
            data = json.loads(p.read_text(encoding="utf-8"))
            return Response(data["url"], data["status"], data["text"], data["ok"], from_cache=True)
        except (json.JSONDecodeError, KeyError, OSError):
            return None

    def _cache_write(self, key: str, resp: Response) -> None:
        try:
            self._cache_path(key).write_text(
                json.dumps({"url": resp.url, "status": resp.status, "text": resp.text, "ok": resp.ok}),
                encoding="utf-8",
            )
        except OSError:
            pass

    # ---- robots.txt ----------------------------------------------------------
    def _get_robots(self, host: str, scheme: str) -> urllib.robotparser.RobotFileParser | None:
        if host in self._robots:
            return self._robots[host]
        rp = urllib.robotparser.RobotFileParser()
        robots_url = f"{scheme}://{host}/robots.txt"
        try:
            r = self.session.get(robots_url, timeout=self.timeout)
            if r.status_code >= 400:
                rp = None  # keine robots.txt -> erlaubt
            else:
                rp.parse(r.text.splitlines())
                cd = rp.crawl_delay(self.user_agent)
                if cd:
                    self._crawl_delay[host] = float(cd)
        except requests.RequestException:
            rp = None
        self._robots[host] = rp
        return rp

    def allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        parsed = urlparse(url)
        rp = self._get_robots(parsed.netloc, parsed.scheme or "https")
        if rp is None:
            return True
        try:
            return rp.can_fetch(self.user_agent, url)
        except Exception:
            return True

    # ---- Rate-Limit ----------------------------------------------------------
    def _throttle(self, host: str) -> None:
        delay = max(self.default_delay, self._crawl_delay.get(host, 0.0))
        last = self._last_host_access.get(host)
        if last is not None:
            wait = delay - (time.time() - last)
            if wait > 0:
                time.sleep(wait)
        self._last_host_access[host] = time.time()

    # ---- GET -----------------------------------------------------------------
    def get(
        self,
        url: str,
        *,
        respect_robots: bool | None = None,
        use_cache: bool = True,
        method: str = "GET",
        data=None,
        headers: dict | None = None,
    ) -> Response:
        cache_key = url if data is None else f"{url}|{json.dumps(data, sort_keys=True)}"
        if use_cache:
            cached = self._cache_read(cache_key)
            if cached is not None:
                return cached

        check_robots = self.respect_robots if respect_robots is None else respect_robots
        if check_robots and not self.allowed(url):
            return Response(url, 0, "", ok=False, error="robots_disallow")

        host = urlparse(url).netloc
        last_err = None
        for attempt in range(self.max_retries + 1):
            self._throttle(host)
            try:
                try:
                    r = self.session.request(
                        method, url, data=data, headers=headers,
                        timeout=self.timeout, allow_redirects=True,
                    )
                except requests.exceptions.SSLError:
                    # kaputtes Zertifikat -> einmal ohne Verifikation versuchen
                    r = self.session.request(
                        method, url, data=data, headers=headers,
                        timeout=self.timeout, allow_redirects=True, verify=False,
                    )
                # Encoding: wenn der Server keinen charset-Header schickt, setzt
                # requests fälschlich ISO-8859-1 -> Umlaute kaputt. Dann erraten.
                ctype = r.headers.get("content-type", "").lower()
                if "charset=" not in ctype:
                    enc = r.apparent_encoding
                    if enc:
                        r.encoding = enc
                ok = 200 <= r.status_code < 300
                resp = Response(str(r.url), r.status_code, r.text, ok)
                if ok and use_cache:
                    self._cache_write(cache_key, resp)
                if r.status_code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                return resp
            except requests.RequestException as e:
                last_err = str(e)
                if attempt < self.max_retries:
                    time.sleep(1.0 * (attempt + 1))
                    continue
        return Response(url, 0, "", ok=False, error=last_err or "request_failed")
