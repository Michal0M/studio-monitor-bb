"""HTML vzorky zostavené podľa REÁLNEJ štruktúry nehnutelnosti.sk overenej 26.9.2026 (texty z reálnych inzerátov v BB)."""


def card(pid, title, ps, img="https://img.unitedclassifieds.sk/foto/x_fss?st=1"):
    anchors = "".join(f'<a href="https://www.nehnutelnosti.sk/detail/{pid}/slug">odkaz</a>' for _ in range(3))
    paras = "".join(f'<p data-test-id="text">{p}</p>' for p in ps)
    return (f'<div class="outer"><div class="card">{anchors}<img src="{img}"><h2>{title}</h2>{paras}'
            f'<a href="https://www.nehnutelnosti.sk/detail/{pid}/slug">viac</a></div></div>')


def page(h1, cards):
    return f'<html><head><title>{h1}</title></head><body><h1>{h1}</h1><main>{"".join(cards)}</main></body></html>'


# reálna karta: "TOP" štítok, cena a €/m² dvakrát, popis až po opakovaní údajov
OFFICE = card("Ju4gHY1H3_h", "Kancelárske Priestory v centre BB na Kapitulskej ulici",
              ["TOP", "Kapitulská 12, Banská Bystrica, okres Banská Bystrica", "Kancelárie, administratívne priestory",
               "33 m²", "265 €/mes.", "8,03 €/m²/mes.",
               "Ponúkame zrekonštruované kancelarske priestory priamo v centre Banskej Bystrice na Kapitulskej ulici, v budove je zavedený optický internet",
               "Luna Capital s.r.o.", "Kancelárie a administratíva Slovensko Prenájom"])
SHOP_BIG = card("RetailBig01", "Na PRENÁJOM lukratívne obchodné priestory 1007 m² v OC Radvaň PARK",
                ["TOP", "Zvolenská cesta 30A, Banská Bystrica, okres Banská Bystrica", "Obchodné priestory", "1007 m²",
                 "10 070 €/mes.", "10 €/m²/mes.",
                 "Na prenájom: priestranné obchodné priestory v OC Radvaň PARK – Banská Bystrica, adresa Zvolenská cesta",
                 "REALITY MARKET, s.r.o."])
AREAL = card("Areal_500", "Na prenájom samostatný prevádzkový areál Banská Bystrica",
             ["Banská Bystrica, okres Banská Bystrica", "Prevádzkový areál", "1350 m²", "Info v RK",
              "ID-500266-14BB Hľadáte nové sídlo firmy? Ponúkame na prenájom obchodno-skladovo-kancelársky objekt.", "TeEq Reality"])
NEGOTIABLE_SMALL = card("Studio_01", "Ateliér / štúdio v centre",
                        ["Horná, Banská Bystrica, okres Banská Bystrica", "Kancelárie, administratívne priestory",
                         "45 m²", "Info v RK", "Kreatívny open space s výkladom, prízemie, vhodné pre fotoštúdio a ateliér.",
                         "Reality X"])
VILLAGE = card("Village_1", "Kancelárie v obci pri meste",
               ["Selce, okres Banská Bystrica", "Kancelárie, administratívne priestory", "60 m²", "300 €/mes.",
                "Kancelárske priestory v obci Selce neďaleko Banskej Bystrice, dobrá dostupnosť z cesty."])

PAGE_OFFICES = page("Kancelárie a administratíva na prenájom, Banská Bystrica", [OFFICE, NEGOTIABLE_SMALL, VILLAGE])
PAGE_SHOPS = page("Obchody na prenájom, Banská Bystrica", [SHOP_BIG])
PAGE_OTHER = page("Iné priestory a objekty na prenájom, Banská Bystrica", [AREAL])
PAGE_EMPTY_NO_H1 = ("<html><head><title>Iné priestory Banská Bystrica - ponuka priestorov na prenájom | Nehnutelnosti.sk</title></head>"
                    "<body><main><p>Žiadne výsledky</p></main></body></html>")
PAGE_GENERIC_REDIRECT = page("Kancelárie a administratíva na prenájom, Slovensko", [OFFICE])

DETAIL_OFFICE = """<html><head><meta name="description" content="Priestor, Prenájom, Banská Bystrica, Kompletná rekonštrukcia, 33 m², 265 €/mes., Ponúkame zrekonštruované..."></head>
<body><main>
<p data-test-id="text">Číslo inzerátu: Ju4gHY1H3_h</p>
<p data-test-id="text">265 €/mes.</p><p data-test-id="text">8,03 €/m²/mes.</p>
<p data-test-id="text">Plocha priestoru:</p><p data-test-id="text">33 m²</p><p data-test-id="text">Kompletná rekonštrukcia</p>
<p data-test-id="text">Podlažie:</p><p data-test-id="text">3 + výťah</p>
<p data-test-id="text">Rok výstavby:</p><p data-test-id="text">1980</p><p data-test-id="text">Tehlová</p>
<p data-test-id="text">Energetický certifikát:</p><p data-test-id="text">nie je</p>
<p data-test-id="text">Vybavenie:</p><p data-test-id="text">Výťah</p>
<p data-test-id="text">Vlastníctvo:</p><p data-test-id="text">Osobné</p>
<p id="detail-description" data-test-id="text">Ponúkame zrekonštruované kancelarske priestory priamo v centre Banskej Bystrice na Kapitulskej ulici, v budove je zavedený optický internet,
Parkovania vo dvore za budovou.
Cena prenájmu 265eur/mes + energie + DPH
- možnosť výberu aj inej kancelarie - rôzne výmery</p>
</main></body></html>"""
