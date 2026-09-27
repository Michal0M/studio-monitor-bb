"""
HTTP vrstva: throttling, ladiace výpisy do logu a JASNÉ rozlíšenie zlyhania zdroja.

Princíp (rovnaký ako pri arteon-monitor): ak niečo nejde (403/429, anti-bot výzva,
zmenená štruktúra), scraper to NEOBÍDE potichu - vyhodí SourceError s dôvodom, zapíše
sa do logu aj do DB (tabuľka source_runs) a zobrazí sa v HTML ako červený pruh.
"""

import time
from dataclasses import dataclass

import requests

import config

HEADERS = {
    "User-Agent": config.USER_AGENT,
    "Accept-Language": "sk,cs;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml",
}

# Reťazce, ktoré v tele odpovede naznačujú anti-bot ochranu (kontroluje sa len keď
# sa v HTML nenašli inzeráty, aby ich náhodný výskyt v texte inzerátu nerobil poplach).
ANTIBOT_MARKERS = ["anubis", "cf-chl", "cf-browser-verification", "just a moment",
                   "captcha", "access denied", "are you a robot", "checking your browser"]


class SourceError(Exception):
    """Zdroj sa nepodarilo spracovať (blokovanie, sieť, zmenená štruktúra)."""

    def __init__(self, kind: str, message: str):
        super().__init__(f"{kind}: {message}")
        self.kind = kind          # 'blocked' | 'network' | 'structure'
        self.message = message


@dataclass
class Page:
    url: str
    status: int
    text: str
    elapsed: float


def _sleep():
    time.sleep(config.REQUEST_DELAY_SECONDS)


def fetch(url: str, log_prefix: str = "", attempts: int = 2) -> Page:
    """
    GET s throttlingom. 403/429 = okamžitý SourceError('blocked') bez opakovania.
    Timeout/5xx: opakuje sa do `attempts` pokusov (predvolene 2, s 10 s pauzou).
    """
    for attempt in range(1, attempts + 1):
        _sleep()
        started = time.time()
        try:
            resp = requests.get(url, headers=HEADERS, timeout=config.REQUEST_TIMEOUT_SECONDS)
        except requests.RequestException as e:
            print(f"{log_prefix} sieťová chyba ({type(e).__name__}) pri {url} [pokus {attempt}]")
            if attempt == attempts:
                raise SourceError("network", f"{type(e).__name__}: {e}") from e
            time.sleep(10)
            continue

        elapsed = time.time() - started
        print(f"{log_prefix} GET {url} -> {resp.status_code}, {len(resp.text)} znakov, {elapsed:.1f}s")

        if resp.status_code in (403, 429):
            raise SourceError("blocked", f"HTTP {resp.status_code} pri {url} "
                                         f"(začiatok odpovede: {resp.text[:160]!r})")
        if resp.status_code >= 500 and attempt < attempts:
            time.sleep(10)
            continue
        if resp.status_code != 200:
            raise SourceError("network", f"HTTP {resp.status_code} pri {url}")
        return Page(url=url, status=resp.status_code, text=resp.text, elapsed=elapsed)
    raise SourceError("network", f"nepodarilo sa stiahnuť {url}")  # pre istotu (nedosiahnuteľné)


def diagnose_empty(page: Page, log_prefix: str = "") -> SourceError:
    """Volá sa, keď HTTP 200 prišlo, ale v HTML sa nenašiel ani jeden inzerát."""
    head = page.text[:4000].lower()
    hit = next((m for m in ANTIBOT_MARKERS if m in head), None)
    print(f"{log_prefix} 0 inzerátov v {page.url}; začiatok HTML: {page.text[:300]!r}")
    if hit:
        return SourceError("blocked", f"stránka vyzerá ako anti-bot výzva (nájdený reťazec '{hit}') pri {page.url}")
    return SourceError("structure", f"HTTP 200, ale žiadne inzeráty v HTML pri {page.url} - zmenila sa štruktúra stránky?")
