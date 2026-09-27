"""
Zdroj: nehnutelnosti.sk - prenájom kancelárií, obchodných a iných priestorov v Banskej Bystrici.

Overené 26.9.2026 v prehliadači:
  - URL: /vysledky/<kategoria>/banska-bystrica/prenajom pre kategórie kancelarie-administrativa, obchody,
    ine-priestory-a-objekty. Iné slugy (kancelarie, ateliery, komercne-priestory) portál potichu presmeruje
    na zoznam za celé Slovensko - preto sa každá stránka overuje cez <h1>/<title> (mesto).
  - Stránka je server-side renderovaná; karta = najmenší spoločný predok odkazov `a[href*="/detail/<ID>/"]`.
  - Poradie <p> v karte: [TOP], lokalita ("Kapitulská 12, Banská Bystrica, okres Banská Bystrica"), druh
    ("Kancelárie, administratívne priestory"), plocha ("33 m²"), cena ("265 €/mes." alebo "Info v RK"),
    cena/m² ("8,03 €/m²/mes."), popis, realitka. Karta obsahuje niektoré údaje dvakrát (mobil/desktop) - deduplikuje sa.
  - Lokalita končí "okres Banská Bystrica" aj pre okolité obce (Selce...), preto sa mesto hľadá mimo časti "okres ...".
  - Detail: dvojice `<p>Plocha priestoru:</p><p>33 m²</p>`, "Podlažie:" ("3 + výťah"), "Vlastníctvo:", celý popis
    v `<p id="detail-description">`, stav v meta description ("Priestor, Prenájom, Banská Bystrica, Kompletná rekonštrukcia, 33 m², ...").
"""

import re

from bs4 import BeautifulSoup

import config
import textutils
from http_util import SourceError, fetch

SOURCE_NAME = "nehnutelnosti_sk"
LABEL = "nehnutelnosti.sk"
REQUIRED = True

_ID_RE = re.compile(r"/detail/([^/]+)/")
_AREA_P = re.compile(r"^[\d\s .,]+m\s*[²2]$")
_PRICE_P = re.compile(r"^\d[\d\s .,]*€(\s*/\s*mes\.?)?$")
_PPM2_P = re.compile(r"€\s*/\s*m\s*[²2]")
_IGNORED_P = {"top", "novinka", "znizena cena", "rezervovane"}
KNOWN_CONDITIONS = {"novostavba", "kompletna rekonstrukcia", "ciastocna rekonstrukcia", "povodny stav",
                    "vo vystavbe", "developersky projekt", "holostav", "dobry stav", "velmi dobry stav"}


def _card_for(anchors):
    first = anchors[0]
    ancestor_ids = [{id(p) for p in a.parents} for a in anchors[1:]]
    for parent in first.parents:
        if all(id(parent) in s for s in ancestor_ids):
            return parent
    return first.parent


def page_is_for(html: str, city_label: str) -> bool:
    """True, ak je to skutočne výpis pre dané mesto (a nie presmerovanie na celé Slovensko). Kontrola <h1> ALEBO <title>."""
    soup = BeautifulSoup(html, "html.parser")
    needle = textutils.fold(city_label)
    h1 = soup.find("h1")
    if h1 and needle in textutils.fold(h1.get_text(" ", strip=True)):
        return True
    return bool(soup.title and needle in textutils.fold(soup.title.get_text(" ", strip=True)))


def location_in_city(location: str | None, city_label: str) -> bool:
    """Mesto musí byť v lokalite MIMO časti 'okres X' (inak by prešla aj obec z okresu Banská Bystrica).
    Bez lokality sa inzerát neodmieta."""
    if not location:
        return True
    needle = textutils.fold(city_label)
    parts = [p for p in location.split(",") if not textutils.fold(p).strip().startswith("okres")]
    return any(needle in textutils.fold(p) for p in parts)


def parse_page(html: str, prop_type: str) -> list[dict]:
    """Kandidáti z jednej stránky výpisu (bez filtrovania kritérií)."""
    soup = BeautifulSoup(html, "html.parser")
    by_id: dict[str, list] = {}
    order: list[str] = []
    for a in soup.select('a[href*="/detail/"]'):
        m = _ID_RE.search(a["href"])
        if not m:
            continue
        pid = m.group(1)
        if pid not in by_id:
            by_id[pid] = []
            order.append(pid)
        by_id[pid].append(a)

    candidates = []
    for pid in order:
        anchors = by_id[pid]
        card = _card_for(anchors)
        h2 = card.find("h2")
        title = h2.get_text(" ", strip=True) if h2 else ""
        paragraphs = []
        for p in card.find_all("p"):
            text = p.get_text(" ", strip=True)
            if text and text not in paragraphs and textutils.fold(text).strip() not in _IGNORED_P:
                paragraphs.append(text)

        location = next((t for t in paragraphs if "okres" in t), None)
        loc_idx = paragraphs.index(location) if location else -1
        area_text = next((t for t in paragraphs if _AREA_P.match(t)), None)
        price_text = next((t for t in paragraphs if _PRICE_P.match(t)), None)
        negotiable = next((t for t in paragraphs if textutils.is_negotiable_price(t)), None)
        ppm2_text = next((t for t in paragraphs if _PPM2_P.search(t)), None)
        subtype = None
        if loc_idx >= 0 and loc_idx + 1 < len(paragraphs):
            cand = paragraphs[loc_idx + 1]
            if not (_AREA_P.match(cand) or _PRICE_P.match(cand) or textutils.is_negotiable_price(cand)
                    or _PPM2_P.search(cand)) and len(cand) < 60:
                subtype = cand
        used = {title, location, area_text, price_text, negotiable, ppm2_text, subtype}
        description = max((t for t in paragraphs if t not in used and len(t) >= 40 and not _PPM2_P.search(t)),
                          key=len, default="")

        img = card.find("img", src=re.compile(r"^https?://"))
        href = anchors[0]["href"]
        candidates.append({
            "portal_id": pid,
            "source": SOURCE_NAME,
            "url": href if href.startswith("http") else config.BASE_NEHNUTELNOSTI + href,
            "title": title,
            "description_raw": description,
            "prop_type": prop_type,
            "subtype": subtype,
            "location": location,
            "area_m2": textutils.parse_area(area_text),
            "price": textutils.parse_price(price_text),
            "price_note": None if price_text else negotiable,
            "price_per_m2": textutils.parse_price_per_m2(ppm2_text),
            "main_photo_url": img["src"] if img else None,
        })
    return candidates


def parse_detail(html: str) -> dict:
    """
    Údaje z detailu: plocha priestoru, podlažie, vlastníctvo, stav, celý popis.
    Dvojice label/hodnota sú za sebou idúce `<p data-test-id="text">`: label končí ':'; ak za labelom hneď
    nasleduje ďalší label, hodnota chýba (None).
    """
    soup = BeautifulSoup(html, "html.parser")
    texts = [p.get_text(" ", strip=True) for p in soup.find_all("p", attrs={"data-test-id": "text"})]
    pairs: dict[str, str | None] = {}
    for i, t in enumerate(texts):
        if t.endswith(":") and len(t) < 40:
            nxt = texts[i + 1] if i + 1 < len(texts) else None
            pairs[t[:-1].strip()] = None if (nxt is None or nxt.endswith(":")) else nxt

    meta = soup.find("meta", attrs={"name": "description"})
    parts = [p.strip() for p in ((meta.get("content") or "") if meta else "").split(",")]
    condition = None
    if len(parts) > 3 and textutils.fold(parts[3]) in KNOWN_CONDITIONS:
        condition = parts[3]

    desc_el = soup.find(id="detail-description")
    return {
        "area_m2": textutils.parse_area(pairs.get("Plocha priestoru")),
        "floor_label": textutils.parse_floor(pairs.get("Podlažie")),
        "ownership": pairs.get("Vlastníctvo"),
        "condition_label": condition,
        "description": desc_el.get_text("\n", strip=True) if desc_el else "",
    }


def fetch_detail(url: str) -> dict:
    page = fetch(url, f"[{SOURCE_NAME}] detail")
    return parse_detail(page.text)


def fetch_all() -> list[dict]:
    """Stiahne všetky kategórie pre mesto. Vyhodí SourceError pri blokovaní / zmenenej štruktúre."""
    prefix = f"[{SOURCE_NAME}]"
    slug, city_label = config.MESTO
    results: dict[str, dict] = {}
    for cat, prop_type in config.KATEGORIE:
        base = config.NEHNUTELNOSTI_URL.format(cat=cat, mesto=slug)
        for page_no in range(1, config.MAX_PAGES_PER_QUERY + 1):
            url = base if page_no == 1 else f"{base}?page={page_no}"
            page = fetch(url, prefix)
            if not page_is_for(page.text, city_label):
                raise SourceError("structure", f"stránka {url} nie je výpisom pre '{city_label}' "
                                               f"(presmerovanie alebo zmena štruktúry)")
            candidates = parse_page(page.text, prop_type)
            print(f"{prefix} {cat}: strana {page_no}, {len(candidates)} inzerátov")
            for c in candidates:
                results.setdefault(c["portal_id"], c)
            if len(candidates) < config.PAGE_SIZE:
                break
        else:
            raise SourceError("structure", f"viac než {config.MAX_PAGES_PER_QUERY} strán pre {base}")
    return list(results.values())
