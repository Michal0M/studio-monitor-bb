"""
Hlavný skript: stiahne inzeráty prenájmu priestorov (kancelárie, obchody, iné) v Banskej Bystrici, vyfiltruje podľa
config.py, zapíše do SQLite a pošle oznámenia na Discord.

  - inzerát, ktorý NESEDÍ na tvrdé kritériá (cena nad strop, plocha mimo rozsahu, iné mesto) -> vymaže sa z DB;
  - inzerát, ktorý sedí, ale zmizol z portálu -> 'removed' (zostane viditeľný);
  - zdroj, ktorý zlyhal alebo dal neúplné dáta -> nič sa neoznačí za stiahnuté, chyba sa zapíše do source_runs.
Exit kód 1, ak zlyhal povinný zdroj.
"""

import sys

import config
import db
import nehnutelnosti_scraper
import notify
import textutils
from http_util import SourceError

SOURCES = [nehnutelnosti_scraper]

DETAIL_KEYS = ("floor_label", "condition_label", "ownership")


def rejection_reason(c: dict) -> str | None:
    """Prečo inzerát nesedí na tvrdé kritériá (None = sedí). Chýbajúca cena/plocha sa NEodmieta."""
    if not nehnutelnosti_scraper.location_in_city(c.get("location"), config.MESTO[1]):
        return f"iné mesto ({c['location']})"
    if textutils.is_demand_ad(c.get("title")):
        return "dopyt (niekto hľadá)"
    if textutils.is_rented(c.get("title")):
        return "už prenajaté"
    if config.PRICE_MAX is not None and c.get("price") is not None and c["price"] > config.PRICE_MAX:
        return f"cena {c['price']:.0f} € nad {config.PRICE_MAX}"
    area = c.get("area_m2")
    if config.MIN_AREA_M2 is not None and area and area < config.MIN_AREA_M2:
        return f"plocha {area:.0f} m² pod {config.MIN_AREA_M2}"
    if config.MAX_AREA_M2 is not None and area and area > config.MAX_AREA_M2:
        return f"plocha {area:.0f} m² nad {config.MAX_AREA_M2}"
    return None


def fix_implausible_price(c: dict) -> dict:
    """Niektoré inzeráty majú v cene chybu portálu/realitky (napr. '1 €/mes.' pri ponuke s viacerými výmerami).
    Takú cenu berieme ako neuvedenú, nie ako skutočnú - inak by prešla ako extrémne lacný inzerát a spustila
    falošné 'price_drop' oznámenie."""
    if c.get("price") is not None and c["price"] < config.MIN_PLAUSIBLE_PRICE:
        c = dict(c)
        c["price_note"] = c["price_note"] or f"Cena v inzeráte neplausibilná ({c['price']:.2f} €/mes.) - berie sa ako neuvedená"
        c["price"] = None
    return c


def enrich(c: dict) -> dict:
    """Doplní príznaky (štúdio, prízemie), energie, DPH a parkovanie z titulku a popisu."""
    c = fix_implausible_price(c)
    c = dict(c)
    text = c.get("description_raw") or ""
    c["flags"] = ",".join(textutils.detect_flags(c["title"], text, c.get("subtype"))) or None
    included, extra = textutils.detect_energy(text)
    c["energy_included"] = None if included is None else int(included)
    c["energy_extra"] = extra
    vat = textutils.detect_vat(f"{c['title']}. {text}")
    c["vat"] = None if vat is None else 1
    c["parking"] = textutils.detect_parking(text)
    return c


def apply_detail(conn, module, raw: dict, budget: dict) -> None:
    """Doplní `raw` o údaje z detailu (podlažie, stav, celý popis). Cache v DB, max DETAIL_MAX_PER_RUN za beh."""
    existing = db.get_listing(conn, db.make_id(module.SOURCE_NAME, raw["portal_id"]))
    if existing:  # prenes uloženú cache, aby ju výpis (ktorý tieto polia nemá) neprepísal
        for key in (*DETAIL_KEYS, "detail_checked_at", "detail_version"):
            raw[key] = existing.get(key)
        if len(existing.get("description_raw") or "") > len(raw.get("description_raw") or ""):
            raw["description_raw"] = existing["description_raw"]
    if not db.detail_is_stale(existing, config.DETAIL_REFRESH_DAYS, config.DETAIL_VERSION):
        return
    if budget["stopped"] or budget["used"] >= config.DETAIL_MAX_PER_RUN:
        budget["skipped"] += 1
        return
    budget["used"] += 1
    try:
        detail = module.fetch_detail(raw["url"])
    except SourceError as e:
        print(f"[{module.SOURCE_NAME}] detail {raw['portal_id']} ZLYHAL ({e.kind}): {e.message}")
        if e.kind in ("blocked", "network"):
            budget["stopped"] = True
            print(f"[{module.SOURCE_NAME}] ďalšie detaily sa v tomto behu nesťahujú")
        budget["failed"] += 1
        return
    for key in DETAIL_KEYS:
        raw[key] = detail.get(key)
    if not raw.get("area_m2") and detail.get("area_m2"):
        raw["area_m2"] = detail["area_m2"]
    if len(detail.get("description") or "") > len(raw.get("description_raw") or ""):
        raw["description_raw"] = detail["description"]
    raw["detail_checked_at"] = db.now_iso()
    raw["detail_version"] = config.DETAIL_VERSION


def process_source(module, conn, pending: list | None = None) -> tuple[str, dict]:
    """Spracuje zdroj. Vracia (status, štatistiky). Oznámenia sa pridávajú do `pending`."""
    name = module.SOURCE_NAME
    print(f"\n=== Zdroj: {module.LABEL} ===")
    try:
        candidates = module.fetch_all()
    except SourceError as e:
        print(f"[{name}] ZLYHALO ({e.kind}): {e.message}")
        db.record_source_run(conn, name, e.kind, None, e.message[:500])
        return e.kind, {}

    stats = {"new": 0, "price_changed": 0, "unchanged": 0, "reappeared": 0, "rejected": 0, "removed": 0}
    budget = {"used": 0, "skipped": 0, "failed": 0, "stopped": False}
    seen = set()
    # prvý beh (prázdna DB pre tento zdroj) = seed: neoznamuje sa nič, inak by prišla stena správ
    seeding = conn.execute("SELECT COUNT(*) FROM listings WHERE source = ?", (name,)).fetchone()[0] == 0
    for raw in candidates:
        seen.add(raw["portal_id"])
        reason = rejection_reason(raw)
        if reason:
            db.delete_listing(conn, name, raw["portal_id"])
            stats["rejected"] += 1
            print(f"[{name}] VYRADENÉ ({reason}): {raw['title'][:70]}")
            continue
        apply_detail(conn, module, raw, budget)
        reason = rejection_reason(raw)   # znova: detail mohol doplniť plochu
        if reason:
            db.delete_listing(conn, name, raw["portal_id"])
            stats["rejected"] += 1
            print(f"[{name}] VYRADENÉ ({reason}): {raw['title'][:70]}")
            continue
        listing = enrich(raw)
        prev = db.get_listing(conn, db.make_id(name, raw["portal_id"]))
        result = db.upsert_listing(conn, listing)
        stats[result] += 1
        if result != "unchanged":
            price = f"{listing['price']:.0f} €" if listing["price"] is not None else (listing["price_note"] or "bez ceny")
            print(f"[{name}] {result.upper()}: {listing['title'][:60]} | {listing['prop_type']} "
                  f"| {listing['area_m2']} m² | {price} | flags={listing['flags']}")
        if pending is not None and not seeding:
            old_price = prev["price"] if prev else None
            kind = notify.kind_for(result, old_price, listing["price"])
            if kind:
                pending.append({"kind": kind, "listing": listing, "old_price": old_price})

    if budget["used"] or budget["skipped"]:
        print(f"[{name}] Detaily: stiahnutých {budget['used'] - budget['failed']}, zlyhalo {budget['failed']}, "
              f"odložených na ďalší beh {budget['skipped']}")
    removed = db.mark_missing_as_removed(conn, name, seen)
    stats["removed"] = len(removed)
    db.record_source_run(conn, name, "ok", len(candidates), None)
    print(f"[{name}] Súhrn: {stats}")
    return "ok", stats


def main() -> int:
    db.init_db(config.DB_PATH)
    with db.connect(config.DB_PATH) as conn:
        cleared = db.clear_implausible_prices(conn, config.MIN_PLAUSIBLE_PRICE)
        if cleared:
            print(f"Vyčistených {cleared} neplauzibilných cien uložených z predchádzajúcich behov.")
    results = []
    pending: list = []
    with db.connect(config.DB_PATH) as conn:
        for module in SOURCES:
            status, _ = process_source(module, conn, pending)
            results.append((module, status))
            conn.commit()
    try:
        notify.send_notifications(pending)
    except Exception as e:  # oznámenia nesmú zhodiť scraper
        print(f"[notify] neočakávaná chyba: {type(e).__name__}")
    failed = [(m, s) for m, s in results if s != "ok"]
    if failed and len(failed) == len(results):
        print("\nVŠETKY zdroje zlyhali - ukončujem s chybou (viď logy vyššie).")
        return 1
    required_failed = [m.LABEL for m, _ in failed if getattr(m, "REQUIRED", True)]
    if required_failed:
        print(f"\nPOVINNÝ zdroj zlyhal: {', '.join(required_failed)} - ukončujem s chybou.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
