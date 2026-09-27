"""
Vygeneruje statickú HTML stránku (docs/index.html) z dát v SQLite. Publikuje sa cez GitHub Pages.
Všetky texty z inzerátov sa escapujú (html.escape).
"""

import html
from datetime import datetime, timezone

import config
import db

SOURCE_LABELS = {"nehnutelnosti_sk": "nehnutelnosti.sk"}
TYPE_LABELS = {"kancelaria": "Kancelária", "obchod": "Obchodný priestor", "ine": "Iný priestor"}
FLAG_LABELS = {
    "studio": ("Štúdio / kreatívne", "Text spomína štúdio, ateliér, showroom, galériu, coworking, open space alebo loft (odhad z textu)"),
    "ground": ("Prízemie / výklad", "Text spomína prízemie, výklad alebo vchod z ulice (odhad z textu)"),
}
PARKING_LABELS = {"included": "Parkovanie", "optional": "Parkovanie (príplatok)", "mentioned": "Parkovanie?"}


def esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def fmt_eur(value) -> str:
    return f"{value:,.0f} €".replace(",", " ")


def fmt_m2(value) -> str:
    return f"{value:,.0f} m²".replace(",", " ")


def category(card: dict) -> str:
    return "removed" if card["status"] != "active" else card["prop_type"]


def price_trend_html(history: list[dict]) -> str:
    prices = [h["price"] for h in history if h["price"] is not None]
    if len(prices) <= 1:
        return ""
    css = "price-down" if prices[-1] < prices[0] else ("price-up" if prices[-1] > prices[0] else "")
    arrow = "↓" if css == "price-down" else ("↑" if css == "price-up" else "→")
    chain = " → ".join(f"{p:,.0f}".replace(",", " ") for p in prices)
    return f'<div class="price-history {css}">{arrow} história: {chain} €</div>'


def price_html(card: dict) -> str:
    if card["price"] is None:
        return f'<div class="card-price dim">{esc(card.get("price_note") or "Cena neuvedená")}</div>'
    extra = ""
    if card.get("vat"):
        extra += " + DPH"
    return f'<div class="card-price">{fmt_eur(card["price"])}<span class="per"> /mes.{extra}</span></div>'


def energy_html(card: dict) -> str:
    """Riadok o energiách a celkovom odhade (ak sú energie navyše so známou sumou)."""
    if card.get("energy_included") == 1:
        return '<div class="plus ok">energie v cene</div>'
    if card.get("energy_included") == 0:
        if card.get("energy_extra") and card["price"] is not None:
            total = card["price"] + card["energy_extra"]
            return (f'<div class="plus">+ energie ~{fmt_eur(card["energy_extra"])}</div>'
                    f'<div class="total-note">spolu ~{fmt_eur(total)} /mes.</div>')
        return '<div class="plus">+ energie (suma neuvedená)</div>'
    return '<div class="plus dim">energie: neuvedené</div>'


def sort_price_per_m2(card: dict) -> float:
    """€/m²/mes.: z portálu, inak cena / plocha; bez údajov 0 (v triedení ide na koniec)."""
    if card.get("price_per_m2"):
        return card["price_per_m2"]
    if card["price"] and card.get("area_m2"):
        return card["price"] / card["area_m2"]
    return 0


def card_html(card: dict, history: list[dict], seed_day: str | None = None) -> str:
    first = datetime.fromisoformat(card["first_seen_at"])
    age_days = (datetime.now(timezone.utc) - first).days
    ppm2 = sort_price_per_m2(card)

    badges = []
    if card["status"] != "active":
        badges.append('<span class="badge badge-sold">Stiahnuté z ponuky</span>')
    elif age_days <= config.NEW_BADGE_DAYS and card["first_seen_at"][:10] != seed_day:
        badges.append('<span class="badge badge-fresh">NOVÉ</span>')
    badges.append(f'<span class="badge badge-type-{esc(card["prop_type"])}">'
                  f'{esc(card.get("subtype") or TYPE_LABELS.get(card["prop_type"], "?"))}</span>')
    for flag in (card.get("flags") or "").split(","):
        if flag in FLAG_LABELS:
            label, tip = FLAG_LABELS[flag]
            badges.append(f'<span class="badge badge-flag" title="{esc(tip)}">{label}</span>')
    if card.get("parking") in PARKING_LABELS:
        badges.append(f'<span class="badge badge-info">{PARKING_LABELS[card["parking"]]}</span>')
    if card.get("condition_label"):
        badges.append(f'<span class="badge badge-info">{esc(card["condition_label"])}</span>')

    photo = card["main_photo_url"]
    if photo:
        photo_html = (f'<img class="card-photo" src="{esc(photo)}" alt="" loading="lazy" referrerpolicy="no-referrer" '
                      f'onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\';">'
                      f'<div class="card-photo card-photo-placeholder" style="display:none;">Bez fotky</div>')
    else:
        photo_html = '<div class="card-photo card-photo-placeholder">Bez fotky</div>'

    meta = []
    if card.get("area_m2"):
        meta.append(fmt_m2(card["area_m2"]))
    if ppm2:
        meta.append(f"{ppm2:,.2f} €/m²/mes.".replace(",", " "))
    if card.get("floor_label"):
        meta.append(esc(card["floor_label"]))
    location = (card.get("location") or "").replace(", okres Banská Bystrica", "")
    loc_html = f'<div class="card-meta">📍 {esc(location)}</div>' if location else ""
    src = SOURCE_LABELS.get(card["source"], card["source"])

    return f"""
    <div class="card" data-cat="{category(card)}" data-type="{esc(card['prop_type'])}" data-pid="{esc(card['portal_id'])}"
         data-price="{card['price'] or 0:.0f}" data-ppm2="{ppm2:.2f}" data-area="{card.get('area_m2') or 0}" data-first="{int(first.timestamp())}">
      <button type="button" class="fav-btn" title="Pridať do obľúbených" aria-label="Pridať do obľúbených" aria-pressed="false">☆</button>
      <a href="{esc(card['url'])}" target="_blank" rel="noopener" class="card-photo-link">{photo_html}</a>
      <div class="card-body">
        <div class="badges">{''.join(badges)}</div>
        <a href="{esc(card['url'])}" target="_blank" rel="noopener" class="card-title">{esc(card['title'])}</a>
        {price_html(card)}
        {energy_html(card)}
        {price_trend_html(history)}
        <div class="card-meta">{' · '.join(meta)}</div>
        {loc_html}
        <div class="card-footer">
          <span class="source-tag"><a href="{esc(card['url'])}" target="_blank" rel="noopener">{esc(src)}</a></span>
          <span class="dates">od {card['first_seen_at'][:10]} · naposledy {card['last_seen_at'][:10]}</span>
        </div>
      </div>
    </div>"""


def run_status_html(runs: dict[str, dict]) -> str:
    if not runs:
        return ""
    parts, problem = [], False
    for source, label in SOURCE_LABELS.items():
        run = runs.get(source)
        if not run:
            parts.append(f"{label}: zatiaľ neprebehol")
        elif run["status"] == "ok":
            parts.append(f'{label}: OK ({run["found"]} inzerátov, {run["run_at"][:16].replace("T", " ")} UTC)')
        else:
            problem = True
            parts.append(f'<b>{label}: ZLYHALO ({esc(run["status"])})</b> - {esc((run["message"] or "")[:200])}'
                         f' ({run["run_at"][:16].replace("T", " ")} UTC)')
    css = "run-status run-problem" if problem else "run-status"
    prefix = "⚠️ Posledný beh zlyhal - dáta môžu byť neaktuálne. " if problem else ""
    return f'<div class="{css}">{prefix}{" · ".join(parts)}</div>'


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="sk">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Štúdio / priestory BB - monitor</title>
<style>
  :root { --bg:#0f1115; --card-bg:#1a1d24; --border:#2a2e38; --text:#e8eaed; --text-dim:#9aa0aa;
          --accent:#4f9dff; --green:#3ecf8e; --red:#ff5c5c; --yellow:#f5c518; }
  * { box-sizing: border-box; }
  body { background:var(--bg); color:var(--text); font-family:-apple-system,"Segoe UI",Roboto,sans-serif; margin:0; padding:16px; }
  h1 { font-size:20px; margin:0 0 4px; }
  .subtitle { color:var(--text-dim); font-size:13px; margin-bottom:12px; }
  .run-status { font-size:12px; color:var(--text-dim); margin-bottom:12px; }
  .run-problem { color:#fff; background:rgba(255,92,92,.18); border:1px solid var(--red); border-radius:6px; padding:8px 10px; }
  .controls { display:flex; gap:8px; margin-bottom:12px; flex-wrap:wrap; align-items:center; }
  .controls button { background:var(--card-bg); border:1px solid var(--border); color:var(--text); padding:6px 12px; border-radius:6px; cursor:pointer; font-size:13px; }
  .controls button.active, .controls button.sort-btn-active { background:var(--accent); border-color:var(--accent); color:#fff; }
  .sort-label { color:var(--text-dim); font-size:13px; }
  .controls button.obec-btn.active { background:var(--accent); border-color:var(--accent); color:#fff; }
  .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(290px,1fr)); gap:14px; }
  .card { background:var(--card-bg); border:1px solid var(--border); border-radius:10px; overflow:hidden; display:flex; flex-direction:column; }
  .card { position:relative; }
  .card[data-cat="removed"] { opacity:.5; }
  .fav-btn { position:absolute; top:8px; right:8px; z-index:2; width:34px; height:34px; border-radius:50%; border:none; cursor:pointer;
             background:rgba(15,17,21,.7); color:#fff; font-size:20px; line-height:34px; padding:0; }
  .fav-btn:hover { background:rgba(15,17,21,.9); }
  .fav-btn.on { color:var(--yellow); }
  .card.is-fav { border-color:var(--yellow); }
  .card-photo-link { display:block; }
  .card-photo { width:100%; height:170px; object-fit:cover; background:#000; display:block; }
  .card-photo-placeholder { align-items:center; justify-content:center; color:var(--text-dim); font-size:12px; background:#15171c; display:flex; }
  .card-body { padding:12px; display:flex; flex-direction:column; gap:6px; }
  .badges { display:flex; gap:4px; flex-wrap:wrap; }
  .badge { font-size:10px; padding:2px 6px; border-radius:4px; font-weight:600; }
  .badge-fresh { background:var(--green); color:#000; }
  .badge-sold { background:var(--red); color:#fff; }
  .badge-type-kancelaria { background:#2a3f5f; color:#9dc4ff; }
  .badge-type-obchod { background:#1f4d3a; color:#8ff0c0; }
  .badge-type-ine { background:#3d2f5a; color:#c9b0ff; }
  .per { font-size:12px; font-weight:500; color:var(--text-dim); }
  .badge-flag { background:#4a3a1a; color:#f0c070; }
  .badge-info { background:#2a2e38; color:var(--text-dim); }
  .badge-warn { background:var(--yellow); color:#000; }
  .card-title { color:var(--text); font-weight:600; font-size:14px; text-decoration:none; line-height:1.3; }
  .card-title:hover { color:var(--accent); }
  .card-price { font-size:20px; font-weight:700; }
  .card-price.dim { font-size:16px; color:var(--text-dim); font-weight:600; }
  .plus { font-size:12px; font-weight:500; color:var(--yellow); }
  .plus.ok { color:var(--green); } .plus.dim { color:var(--text-dim); }
  .total-note { font-size:12px; color:var(--yellow); margin-top:-4px; }
  .price-history { font-size:11px; color:var(--text-dim); }
  .price-history.price-down { color:var(--green); } .price-history.price-up { color:var(--red); }
  .card-meta { font-size:12px; color:var(--text-dim); }
  .card-footer { display:flex; justify-content:space-between; gap:8px; flex-wrap:wrap; font-size:10px; color:var(--text-dim); margin-top:4px; border-top:1px solid var(--border); padding-top:6px; }
  .card-footer a { color:var(--accent); }
  .empty-state { color:var(--text-dim); padding:40px; text-align:center; }
</style>
</head>
<body>
  <h1>🏢 Priestory na prenájom · Banská Bystrica</h1>
  <div class="subtitle">Aktualizované: %%UPDATED%% · %%OBCE%% · prenájom · štúdio / ateliér / kancelárie</div>
  %%RUN_STATUS%%
  <div class="controls">
    <button class="filter-btn" data-filter="fav" data-label="★ Obľúbené">★ Obľúbené (0)</button>
    <button class="filter-btn active" data-filter="all" data-label="Všetky aktívne">Všetky aktívne (%%N_ALL%%)</button>
    <button class="filter-btn" data-filter="kancelaria" data-label="Kancelárie">Kancelárie (%%N_KANCELARIA%%)</button>
    <button class="filter-btn" data-filter="obchod" data-label="Obchodné">Obchodné (%%N_OBCHOD%%)</button>
    <button class="filter-btn" data-filter="ine" data-label="Iné priestory">Iné priestory (%%N_INE%%)</button>
    <button class="filter-btn" data-filter="removed" data-label="Stiahnuté">Stiahnuté (%%N_REMOVED%%)</button>
  </div>
  <div class="controls">
    <span class="sort-label">Zoradiť:</span>
    <button class="sort-btn sort-btn-active" data-field="price">Cena</button>
    <button class="sort-btn" data-field="ppm2">€/m²/mes.</button>
    <button class="sort-btn" data-field="area">Plocha</button>
    <button class="sort-btn" data-field="first">Najnovšie</button>
  </div>
  <div id="grid" class="grid">
    %%CARDS%%
  </div>
  <div id="empty" class="empty-state" style="display:none;">Žiadne inzeráty v tomto filtri.</div>

<script>
  const grid = document.getElementById('grid');
  const empty = document.getElementById('empty');
  const cards = Array.from(grid.children);
  let currentFilter = 'all';
  const sortState = { field: 'price', asc: true };
  const DEFAULT_ASC = { price: true, ppm2: true, area: false, first: false };

  // Obľúbené: ukladajú sa len v tomto prehliadači (localStorage), kľúčom je ID inzerátu.
  const FAV_KEY = 'studio-bb-favs';
  let favs = new Set();
  try { favs = new Set(JSON.parse(localStorage.getItem(FAV_KEY) || '[]')); } catch (e) {}
  const saveFavs = () => { try { localStorage.setItem(FAV_KEY, JSON.stringify([...favs])); } catch (e) {} };
  const isFav = c => favs.has(c.dataset.pid);
  function paintFavs() {
    cards.forEach(c => {
      const on = isFav(c), b = c.querySelector('.fav-btn');
      b.textContent = on ? '★' : '☆';
      b.classList.toggle('on', on);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
      b.title = on ? 'Odstrániť z obľúbených' : 'Pridať do obľúbených';
      c.classList.toggle('is-fav', on);
    });
  }

  const active = c => c.dataset.cat !== 'removed';
  const catOk = (c, f) => f === 'fav' ? isFav(c) : (f === 'removed' ? !active(c)
      : (active(c) && (f === 'all' || c.dataset.type === f)));

  function updateCounts() {
    document.querySelectorAll('.filter-btn').forEach(btn => {
      const n = cards.filter(c => catOk(c, btn.dataset.filter)).length;
      btn.textContent = btn.dataset.label + ' (' + n + ')';
    });
  }

  function applyFilter() {
    let visible = 0;
    cards.forEach(c => {
      const show = catOk(c, currentFilter);
      c.style.display = show ? '' : 'none';
      if (show) visible++;
    });
    empty.style.display = visible === 0 ? 'block' : 'none';
    updateCounts();
  }

  function applySort() {
    const value = c => parseFloat(c.dataset[sortState.field]) || 0;
    cards.slice().sort((a, b) => {
      const fa = isFav(a), fb = isFav(b);
      if (fa !== fb) return fa ? -1 : 1;          // obľúbené vždy na začiatku
      const va = value(a), vb = value(b);
      if (sortState.asc && (va === 0 || vb === 0) && va !== vb) return va === 0 ? 1 : -1;  // bez údaja na koniec
      return sortState.asc ? va - vb : vb - va;
    }).forEach(c => grid.appendChild(c));
  }

  function updateSortLabels() {
    document.querySelectorAll('.sort-btn').forEach(btn => {
      const on = btn.dataset.field === sortState.field;
      btn.classList.toggle('sort-btn-active', on);
      btn.textContent = btn.textContent.replace(/ [↑↓]$/, '') + (on ? (sortState.asc ? ' ↑' : ' ↓') : '');
    });
  }

  document.querySelectorAll('.filter-btn').forEach(btn => btn.addEventListener('click', () => {
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentFilter = btn.dataset.filter;
    applyFilter();
  }));

  grid.addEventListener('click', e => {
    const b = e.target.closest('.fav-btn');
    if (!b) return;
    const c = b.closest('.card');
    if (favs.has(c.dataset.pid)) favs.delete(c.dataset.pid); else favs.add(c.dataset.pid);
    saveFavs(); paintFavs(); applySort(); applyFilter();
  });

  document.querySelectorAll('.sort-btn').forEach(btn => btn.addEventListener('click', () => {
    if (sortState.field === btn.dataset.field) sortState.asc = !sortState.asc;
    else { sortState.field = btn.dataset.field; sortState.asc = DEFAULT_ASC[btn.dataset.field]; }
    updateSortLabels(); applySort();
  }));

  paintFavs(); updateSortLabels(); applySort(); applyFilter();
</script>
</body>
</html>
"""


def render(db_path: str | None = None, output_path: str | None = None) -> str:
    db_path = db_path or config.DB_PATH
    output_path = output_path or config.OUTPUT_HTML_PATH
    with db.connect(db_path) as conn:
        cards = db.get_all_listings(conn)
        seed_day = min((r["first_seen_at"][:10] for r in cards), default=None)
        histories = {c["id"]: db.get_price_history(conn, c["id"]) for c in cards}
        runs = db.last_source_runs(conn)

    cards.sort(key=lambda c: (c["price"] is None, c["price"] or 0))
    counts = {"kancelaria": 0, "obchod": 0, "ine": 0, "removed": 0}
    for c in cards:
        counts[category(c)] += 1

    page = (PAGE_TEMPLATE
            .replace("%%UPDATED%%", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
            .replace("%%OBCE%%", esc(config.MESTO[1]))
            .replace("%%RUN_STATUS%%", run_status_html(runs))
            .replace("%%N_KANCELARIA%%", str(counts["kancelaria"])).replace("%%N_OBCHOD%%", str(counts["obchod"]))
            .replace("%%N_INE%%", str(counts["ine"])).replace("%%N_REMOVED%%", str(counts["removed"]))
            .replace("%%N_ALL%%", str(counts["kancelaria"] + counts["obchod"] + counts["ine"]))
            .replace("%%CARDS%%", "\n".join(card_html(c, histories[c["id"]], seed_day) for c in cards)))

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"Vygenerované: {output_path} ({len(cards)} kariet: {counts})")
    return page


if __name__ == "__main__":
    render()
