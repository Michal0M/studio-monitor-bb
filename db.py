"""
SQLite vrstva: inzeráty, história cien a záznamy o behoch zdrojov.

Tabuľky:
    listings      - jeden riadok = jeden inzerát prenájmu na jednom portáli (aktuálny stav).
    price_history - append-only log cien.
    source_runs   - výsledok posledných behov zdroja (ok / blocked / network / structure),
                    aby bolo vidno, že zdroj zlyhal, a nie že "nič nové".
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    id                TEXT PRIMARY KEY,      -- '<source>:<portal_id>'
    source            TEXT NOT NULL,
    portal_id         TEXT NOT NULL,
    url               TEXT NOT NULL,
    title             TEXT NOT NULL,
    description_raw   TEXT,
    prop_type         TEXT NOT NULL,         -- kancelaria / obchod / ine
    subtype           TEXT,                  -- 'Kancelárie, administratívne priestory', 'Obchodné priestory'...
    location          TEXT,                  -- 'Kapitulská 12, Banská Bystrica, okres Banská Bystrica'
    area_m2           REAL,
    price             REAL,                  -- €/mesiac; NULL = 'Info v RK' / neuvedená
    price_note        TEXT,                  -- napr. 'Info v RK'
    price_per_m2      REAL,                  -- €/m²/mes. z portálu
    floor_label       TEXT,                  -- 'prízemie', '3. poschodie (výťah)'
    condition_label   TEXT,                  -- stav z detailu (Kompletná rekonštrukcia...)
    ownership         TEXT,
    energy_included   INTEGER,               -- 1 = energie v cene, 0 = navyše, NULL = neuvedené
    energy_extra      REAL,                  -- suma energií navyše, ak je v texte
    vat               INTEGER,               -- 1 = v texte je "+ DPH", NULL = neuvedené
    parking           TEXT,                  -- included / optional / mentioned
    flags             TEXT,                  -- čiarkou: studio, ground
    main_photo_url    TEXT,
    status            TEXT DEFAULT 'active', -- active / removed
    detail_checked_at TEXT,
    detail_version    INTEGER,
    first_seen_at     TEXT NOT NULL,
    last_seen_at      TEXT NOT NULL,
    removed_at        TEXT
);

CREATE TABLE IF NOT EXISTS price_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id  TEXT NOT NULL,
    price       REAL,
    recorded_at TEXT NOT NULL,
    FOREIGN KEY (listing_id) REFERENCES listings(id)
);

CREATE TABLE IF NOT EXISTS source_runs (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    source    TEXT NOT NULL,
    run_at    TEXT NOT NULL,
    status    TEXT NOT NULL,
    found     INTEGER,
    message   TEXT
);

CREATE INDEX IF NOT EXISTS idx_price_history_listing ON price_history(listing_id);
CREATE INDEX IF NOT EXISTS idx_listings_status ON listings(status);
"""

_COLUMNS = ["source", "portal_id", "url", "title", "description_raw", "prop_type", "subtype", "location",
            "area_m2", "price", "price_note", "price_per_m2", "floor_label", "condition_label", "ownership",
            "energy_included", "energy_extra", "vat", "parking", "flags", "main_photo_url", "detail_checked_at",
            "detail_version"]


# Stĺpce pridané po prvom nasadení - ALTER TABLE pre už existujúce DB súbory. Bezpečné spúšťať opakovane.
_MIGRATIONS: list[tuple[str, str]] = []


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: str) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(listings)")}
        for column, ctype in _MIGRATIONS:
            if column not in existing:
                conn.execute(f"ALTER TABLE listings ADD COLUMN {column} {ctype}")


def make_id(source: str, portal_id: str) -> str:
    return f"{source}:{portal_id}"


def get_listing(conn, listing_id: str):
    row = conn.execute("SELECT * FROM listings WHERE id = ?", (listing_id,)).fetchone()
    return dict(row) if row else None


def upsert_listing(conn, listing: dict) -> str:
    """
    Vloží alebo aktualizuje inzerát. Vracia 'new' | 'price_changed' | 'unchanged' | 'reappeared'.
    Zmena ceny (aj NULL -> číslo) pridá riadok do price_history. Prechod čísla na NULL ("Cena dohodou")
    sa berie ako "neuvedená" a ako zmena ceny sa NEráta (posledná známa cena ostane).
    """
    listing_id = make_id(listing["source"], listing["portal_id"])
    existing = get_listing(conn, listing_id)
    ts = now_iso()
    values = [listing.get(c) for c in _COLUMNS]

    if existing is None:
        conn.execute(
            f"INSERT INTO listings (id, {', '.join(_COLUMNS)}, status, first_seen_at, last_seen_at) "
            f"VALUES (?, {', '.join('?' for _ in _COLUMNS)}, 'active', ?, ?)",
            [listing_id, *values, ts, ts],
        )
        conn.execute("INSERT INTO price_history (listing_id, price, recorded_at) VALUES (?, ?, ?)",
                     (listing_id, listing.get("price"), ts))
        return "new"

    was_removed = existing["status"] != "active"
    new_price = listing.get("price")
    price_changed = new_price is not None and existing["price"] != new_price
    if new_price is None:   # ponechaj poslednú známu cenu
        idx = _COLUMNS.index("price")
        values[idx] = existing["price"]

    conn.execute(
        f"UPDATE listings SET {', '.join(c + ' = ?' for c in _COLUMNS)}, "
        "status = 'active', last_seen_at = ?, removed_at = NULL WHERE id = ?",
        [*values, ts, listing_id],
    )
    if price_changed:
        conn.execute("INSERT INTO price_history (listing_id, price, recorded_at) VALUES (?, ?, ?)",
                     (listing_id, new_price, ts))
        return "price_changed"
    return "reappeared" if was_removed else "unchanged"


def detail_is_stale(existing: dict | None, max_age_days: int, version: int | None = None) -> bool:
    """True, ak sa detail ešte nesťahoval, je starší než max_age_days alebo bol stiahnutý staršou verziou parsera."""
    if existing is None or not existing.get("detail_checked_at"):
        return True
    if version is not None and existing.get("detail_version") != version:
        return True
    checked = datetime.fromisoformat(existing["detail_checked_at"])
    return (datetime.now(timezone.utc) - checked).days >= max_age_days


def delete_listing(conn, source: str, portal_id: str) -> bool:
    """Natvrdo zmaže inzerát + históriu (keď prestal sedieť na kritériá - NIE keď zmizol z portálu)."""
    listing_id = make_id(source, portal_id)
    # Najprv "dieťa" (price_history), potom "rodič" (listings) - foreign_keys je zapnuté.
    conn.execute("DELETE FROM price_history WHERE listing_id = ?", (listing_id,))
    return conn.execute("DELETE FROM listings WHERE id = ?", (listing_id,)).rowcount > 0


def mark_missing_as_removed(conn, source: str, seen_portal_ids: set[str]) -> list[str]:
    """
    Aktívne inzeráty zdroja, ktoré v tomto (ÚPLNOM a úspešnom) behu neboli vo výpise,
    sa označia 'removed'. Volá sa LEN po úspešnom kompletnom behu zdroja - pri chybe
    (403, timeout, neúplné stránkovanie) sa NEvolá, aby výpadok siete neoznačil
    všetky inzeráty za stiahnuté.
    """
    rows = conn.execute("SELECT id, portal_id FROM listings WHERE source = ? AND status = 'active'",
                        (source,)).fetchall()
    removed = []
    ts = now_iso()
    for row in rows:
        if row["portal_id"] not in seen_portal_ids:
            conn.execute("UPDATE listings SET status = 'removed', removed_at = ? WHERE id = ?", (ts, row["id"]))
            removed.append(row["id"])
    return removed


def get_price_history(conn, listing_id: str) -> list[dict]:
    rows = conn.execute("SELECT price, recorded_at FROM price_history WHERE listing_id = ? "
                        "ORDER BY recorded_at, id", (listing_id,)).fetchall()
    return [dict(r) for r in rows]


def get_all_listings(conn) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM listings ORDER BY price IS NULL, price ASC").fetchall()]


def record_source_run(conn, source: str, status: str, found: int | None, message: str | None) -> None:
    conn.execute("INSERT INTO source_runs (source, run_at, status, found, message) VALUES (?, ?, ?, ?, ?)",
                 (source, now_iso(), status, found, message))


def last_source_runs(conn) -> dict[str, dict]:
    """Posledný záznam behu pre každý zdroj."""
    rows = conn.execute(
        "SELECT r.* FROM source_runs r JOIN (SELECT source, MAX(id) AS mid FROM source_runs GROUP BY source) m "
        "ON r.id = m.mid").fetchall()
    return {r["source"]: dict(r) for r in rows}
