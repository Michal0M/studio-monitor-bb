# studio-monitor-bb

Denný monitor **prenájmu priestorov (štúdio / ateliér / kancelárie) v Banskej Bystrici** z nehnutelnosti.sk.
GitHub Actions ho spustí raz denne, uloží dáta do SQLite (`data/listings.db`), vygeneruje stránku `docs/index.html`
(GitHub Pages) a pošle novinky na Discord (`#štúdio-bb`).

## Čo sleduje
Kategórie `kancelarie-administrativa`, `obchody`, `ine-priestory-a-objekty` (portál nemá samostatnú kategóriu "ateliér"/"štúdio";
ateliéry sú v týchto troch). Príznak "Štúdio / kreatívne" je odhad z textu (ateliér, štúdio, showroom, open space, loft...).

## Nastavenia (`config.py`)
- `PRICE_MAX = 1500` €/mes., `MIN_AREA_M2 = 15`, `MAX_AREA_M2 = 250`. Inzerát bez ceny ("Info v RK") alebo bez plochy sa neodmieta.
- `KATEGORIE` - pridaj/odober kategórie (slugy musia byť overené v prehliadači, zlé portál presmeruje na celé Slovensko
  a scraper to ohlási ako chybu `structure`).

## Stránka
Filtre Kancelárie / Obchodné / Iné / ★ Obľúbené / Stiahnuté, zoradenie (cena, €/m²/mes., plocha, najnovšie).
Obľúbené sa ukladajú v prehliadači (localStorage) a idú vždy navrchu. Pri energiách navyše so známou sumou sa ráta "spolu".

## Discord
Webhook je v GitHub Secret `DISCORD_WEBHOOK_STUDIO` (nikdy v kóde). Prvý beh je "seed" (bez oznámení). Ďalej: nový inzerát,
zľava, zvýšenie ceny, zverejnenie ceny, opäť v ponuke. Max 15 oznámení na beh. Test: Actions -> Run workflow -> zaškrtni "discord_test".

## Testy
`python -m unittest discover -s tests -v`
