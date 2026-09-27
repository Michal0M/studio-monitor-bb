"""
Nastavenia monitora prenájmu priestorov pre štúdio / ateliér v Banskej Bystrici (kancelárie, obchodné a iné priestory).
Uprav tento súbor, keď chceš zmeniť cenu, veľkosť alebo kategórie.
"""

# --- Čo hľadáme ---
MESTO = ("banska-bystrica", "Banská Bystrica")   # (slug na nehnutelnosti.sk, názov)

# (slug kategórie na nehnutelnosti.sk, náš kľúč). Overené 26.9.2026 v prehliadači. Kategórie 'sklady', 'vyroba',
# 'restauracie' sa zámerne nesledujú (nie sú pre štúdio); pridáš ich sem. Slug 'kancelarie', 'ateliery',
# 'komercne-priestory' NEfungujú (portál ich presmeruje na celé Slovensko).
KATEGORIE = [
    ("kancelarie-administrativa", "kancelaria"),
    ("obchody", "obchod"),
    ("ine-priestory-a-objekty", "ine"),
]

# Tvrdé filtre (None = bez limitu). Inzerát mimo limitov sa z DB vymaže (zmenou limitu sa vráti ako nový).
# Inzerát BEZ ceny ("Info v RK") alebo bez plochy sa nikdy neodmieta.
PRICE_MAX = 1500       # €/mesiac (nájom bez energií, ako je v inzeráte)

# Niektoré inzeráty (viac výmer v jednom ozname) majú v cene chybu realitky - napr. "1 €/mes." alebo "4,5 €/mes."
# namiesto skutočnej ceny (overené 27.9.2026 na živých dátach). Cena pod touto hranicou sa berie ako neuvedená,
# NIE ako skutočná cena (a teda sa inzerát needmieta a nedostane oznámenie "price_drop" na absurdne nízku sumu).
MIN_PLAUSIBLE_PRICE = 20
MIN_AREA_M2 = 15
MAX_AREA_M2 = 250      # odfiltruje haly a celé areály (napr. 1350 m² prevádzkový areál)

# --- Zdroj ---
BASE_NEHNUTELNOSTI = "https://www.nehnutelnosti.sk"
NEHNUTELNOSTI_URL = BASE_NEHNUTELNOSTI + "/vysledky/{cat}/{mesto}/prenajom"

# --- Technické nastavenia scrapera ---
REQUEST_DELAY_SECONDS = 4
REQUEST_TIMEOUT_SECONDS = 20
USER_AGENT = "Mozilla/5.0 (compatible; studio-monitor-bb/1.0; osobne pouzitie, 1 beh denne)"
PAGE_SIZE = 30
MAX_PAGES_PER_QUERY = 6

DETAIL_REFRESH_DAYS = 14         # detail (podlažie, stav, celý popis) sa obnovuje raz za N dní
DETAIL_MAX_PER_RUN = 100
DETAIL_VERSION = 1

NEW_BADGE_DAYS = 3               # "NOVÉ" badge; pri úplne prvom behu sa nezobrazuje

DB_PATH = "data/listings.db"
OUTPUT_HTML_PATH = "docs/index.html"

# --- Discord oznámenia (webhook v GitHub Secret DISCORD_WEBHOOK_STUDIO) ---
NOTIFY_MAX_PER_RUN = 15
