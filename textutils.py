"""Pomocné funkcie na čísla a text z inzerátov (bez diakritiky/malými písmenami cez fold(), € -> ' eur ')."""

import re
import unicodedata

NBSP = " "


def fold(text: str | None) -> str:
    """Malé písmená, bez diakritiky, € -> ' eur ', zjednotené medzery."""
    if not text:
        return ""
    s = text.replace("€", " eur ").replace(NBSP, " ")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"\s+", " ", s)


def fold_lines(text: str | None) -> str:
    """Ako fold(), ale koniec riadku sa zmení na ". " (položky po riadkoch by sa inak zlepili)."""
    return fold(re.sub(r"\s*[\r\n]+\s*", ". ", text or ""))


# ------------------------------------------------------------------ čísla

def parse_price(text: str | None) -> float | None:
    """'265 €/mes.' -> 265.0, '1 800 €/mes.' -> 1800.0. Cena za m² ('8,03 €/m²/mes.') sa NEberie."""
    if not text:
        return None
    t = text.replace(NBSP, " ").strip()
    if re.search(r"€\s*/\s*m\s*[²2]", t):
        return None
    m = re.search(r"(\d[\d ]*(?:[.,]\d{1,2})?)\s*€", t)
    if not m:
        return None
    try:
        return float(m.group(1).replace(" ", "").replace(",", "."))
    except ValueError:
        return None


def parse_price_per_m2(text: str | None) -> float | None:
    """'8,03 €/m²/mes.' -> 8.03."""
    if not text:
        return None
    m = re.search(r"(\d[\d ]*(?:[.,]\d+)?)\s*€\s*/\s*m\s*[²2]", text.replace(NBSP, " "))
    return float(m.group(1).replace(" ", "").replace(",", ".")) if m else None


def parse_area(text: str | None) -> float | None:
    """'33 m²' -> 33.0, '74,91 m2' -> 74.91."""
    if not text:
        return None
    m = re.search(r"(\d[\d ]*(?:[.,]\d+)?)\s*m\s*[²2]", text.replace(NBSP, " "))
    return float(m.group(1).replace(" ", "").replace(",", ".")) if m else None


def is_negotiable_price(text: str | None) -> bool:
    """'Info v RK', 'Cena dohodou', 'Cena na vyžiadanie' - cena nie je číslo."""
    t = fold(text).strip()
    return bool(re.match(r"^(info v rk|cena (dohodou|na vyziadanie|v rk|nezname)|dohodou|na vyziadanie)", t))


def parse_floor(text: str | None) -> str | None:
    """'3 + výťah' -> '3. poschodie (výťah)', '2' -> '2. poschodie', 'Prízemie' -> 'prízemie'; inak pôvodný text."""
    if not text:
        return None
    t = fold(text)
    if "prizemi" in t or t.strip() in ("0", "pr"):
        return "prízemie"
    m = re.match(r"(\d+)", t.strip())
    if m:
        return f"{m.group(1)}. poschodie" + (" (výťah)" if "vytah" in t else "")
    return text.strip()


# ------------------------------------------------------------------ energie, DPH

_ENERGY_EXTRA_PATTERNS = [
    r"(\d{2,3})(?:,-)?\s*eur\w*\s*/?\s*(?:mesiac|mesacne|mes)?\s*(?:za\s+|na\s+)?(?:zalohy?\s+(?:na\s+)?)?energi",
    r"energi\w*(?:\s*(?:a|\+|,|/)\s*(?:sprav\w*|poplat\w*|internet\w*|odpad\w*))*"
    r"\s*(?:cca|asi|ca|priblizne|okolo|vo vyske|:|-)?\s*(?:cca\s*)?(\d{2,3})(?:,-)?\s*eur",
    r"zalohy?\s+(?:na\s+)?energi\w*\s*(?:cca|vo vyske|:)?\s*(\d{2,3})\b",
]
_ENERGY_INCLUDED = (
    r"(?:vratane|s|v cene)\s+(?:vsetk\w+\s+)?(?:energi|inkasa)|energi\w*\s+(?:su\s+)?(?:v\s+cene|zahrnut)"
    r"|cena\s+(?:je\s+)?(?:kompletna|vratane)|zahrna\w*\s+(?:zalohov\w+\s+platby\s+za\s+)?energi"
)
_ENERGY_EXCLUDED = r"bez\s+energi|\+\s*energi|plus\s+energi|energi\w*\s+(?:navyse|zvlast|hradi|sa\s+plat)"


def detect_energy(text: str | None) -> tuple[bool | None, float | None]:
    """(energie_v_cene True/False/None, mesačná suma energií navyše 20-800 € ak sa dala vyčítať)."""
    t = fold_lines(text).replace("~", " cca ")
    extra = None
    for pattern in _ENERGY_EXTRA_PATTERNS:
        m = re.search(pattern, t)
        if m and 20 <= float(m.group(1)) <= 800:
            extra = float(m.group(1))
            break
    included = None
    if extra is not None or re.search(_ENERGY_EXCLUDED, t):
        included = False
    elif re.search(_ENERGY_INCLUDED, t):
        included = True
    return included, extra


def detect_vat(text: str | None) -> bool | None:
    """True = nájom je + DPH (plus DPH, bez DPH), False = výslovne 'bez DPH' nie je uvedené... vracia len True/None.
    Zámerne: None = neuvedené (nie je dôkaz, že DPH nie je)."""
    t = fold(text)
    return True if re.search(r"\+\s*dph|plus\s+dph|bez\s+dph|cena\s+je\s+bez\s+dph|najom\w*\s+bez\s+dph|dph\s+(?:sa\s+)?(?:uctuje|navyse)", t) else None


# ------------------------------------------------------------------ parkovanie

_PARK_WORD = r"parkovac|parkovan|parking|garaz|statie|carport"
_PARK_NEG = r"bez\s+(?:parkovan|garaz)|nema\s+(?:parkovan|garaz)|parkovan\w*\s+(?:nie je|nemozne)"
_PARK_OPTIONAL = (r"prikupit|dokupit|priplatok|za\s+poplatok|prenajat\s+si\s+(?:zvlast|samostatne)"
                  r"|moznost\w*\s+(?:prenaj\w+|prikup\w+|dokup\w+)|volitelne|zvlast")
_PARK_INCLUDED = r"sucastou|v\s+cene|vratane|vlastn\w+|vyhraden\w+|pridelen\w+|pre\s+najomcov|vo\s+dvore|za\s+budovou|pred\s+budovou"


def detect_parking(text: str | None) -> str | None:
    """'included' | 'optional' | 'mentioned' | None (informácia, nie filter)."""
    found = None
    rank = {"mentioned": 1, "optional": 2, "included": 3}
    for sentence in re.split(r"[.!?;]", fold_lines(text)):
        if not re.search(_PARK_WORD, sentence) or re.search(_PARK_NEG, sentence):
            continue
        if re.search(_PARK_OPTIONAL, sentence):
            kind = "optional"
        elif re.search(_PARK_INCLUDED, sentence):
            kind = "included"
        else:
            kind = "mentioned"
        if found is None or rank[kind] > rank[found]:
            found = kind
    return found


# ------------------------------------------------------------------ príznaky, stav

_STUDIO = re.compile(r"atelier|studio|fotostudi|foto studi|showroom|galeri|coworking|co-working|open ?space|loft|"
                     r"natacan|videostudi|podcast|kreativn")
_GROUND = re.compile(r"\bprizemi|vyklad|vlastny vchod z ulice|pristup z ulice")


def detect_flags(title: str | None, description: str | None, subtype: str | None = None) -> list[str]:
    """
      studio - text spomína štúdio/ateliér/showroom/galériu/coworking/open space/loft/kreatívny priestor
      ground - prízemie / výklad / vchod z ulice (vhodné pre zákazníkov)
    Sú to odhady z textu, nie fakty."""
    text = fold(f"{title or ''}. {description or ''}")
    flags = []
    if _STUDIO.search(text):
        flags.append("studio")
    if _GROUND.search(text):
        flags.append("ground")
    return flags


def is_reserved(title: str | None) -> bool:
    return bool(re.search(r"\brezervovan", fold(title)))


def is_rented(title: str | None) -> bool:
    return bool(re.search(r"\bprenajat|\bobsaden", fold(title)))


def is_demand_ad(title: str | None) -> bool:
    return bool(re.match(r"(dopyt|hladam\b|hladame\b|prenajmem si\b)", fold(title).strip()))
