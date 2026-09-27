import os
import tempfile
import unittest
from unittest import mock

import config
import db
import nehnutelnosti_scraper as ns
import notify
import render
import scraper
import textutils as tu
from tests import fixtures as fx


class TextutilsTests(unittest.TestCase):
    def test_numbers(self):
        self.assertEqual(tu.parse_price("265 €/mes."), 265.0)
        self.assertEqual(tu.parse_price("1 800 €/mes."), 1800.0)
        self.assertIsNone(tu.parse_price("8,03 €/m²/mes."))
        self.assertIsNone(tu.parse_price("Info v RK"))
        self.assertEqual(tu.parse_price_per_m2("8,03 €/m²/mes."), 8.03)
        self.assertEqual(tu.parse_area("1 007 m²"), 1007.0)
        self.assertTrue(tu.is_negotiable_price("Info v RK"))
        self.assertEqual(tu.parse_floor("3 + výťah"), "3. poschodie (výťah)")
        self.assertEqual(tu.parse_floor("Prízemie"), "prízemie")

    def test_energy_vat_parking_real_text(self):
        real = ("Ponúkame zrekonštruované kancelarske priestory.\nParkovania vo dvore za budovou.\n"
                "Cena prenájmu 265eur/mes + energie + DPH\n- možnosť výberu aj inej kancelarie")
        self.assertEqual(tu.detect_energy(real), (False, None))
        self.assertTrue(tu.detect_vat(real))
        self.assertEqual(tu.detect_parking(real), "included")
        self.assertEqual(tu.detect_energy("Nájom 300 € vrátane energií."), (True, None))
        self.assertEqual(tu.detect_energy("Energie cca 80 € mesačne navyše"), (False, 80.0))
        self.assertEqual(tu.detect_energy("Nájom + energie ~90 € + DPH"), (False, 90.0))
        self.assertEqual(tu.detect_energy("Pekný priestor"), (None, None))
        self.assertIsNone(tu.detect_vat("Pekný priestor"))
        self.assertEqual(tu.detect_parking("Bez parkovania."), None)

    def test_flags(self):
        self.assertEqual(tu.detect_flags("Ateliér", "open space s výkladom, prízemie"), ["studio", "ground"])
        self.assertEqual(tu.detect_flags("Kancelária", "Klasické kancelárske priestory na treťom poschodí"), [])

    def test_ads(self):
        self.assertTrue(tu.is_demand_ad("Hľadám priestor na ateliér"))
        self.assertTrue(tu.is_rented("PRENAJATÉ - kancelária"))
        self.assertFalse(tu.is_rented("Kancelária na prenájom"))


class ParserTests(unittest.TestCase):
    def test_office_cards(self):
        c = {x["portal_id"]: x for x in ns.parse_page(fx.PAGE_OFFICES, "kancelaria")}
        self.assertEqual(len(c), 3)
        o = c["Ju4gHY1H3_h"]                                   # ID s podčiarkovníkom; "TOP" sa ignoruje
        self.assertEqual(o["subtype"], "Kancelárie, administratívne priestory")
        self.assertEqual(o["area_m2"], 33.0)
        self.assertEqual(o["price"], 265.0)
        self.assertEqual(o["price_per_m2"], 8.03)
        self.assertEqual(o["location"], "Kapitulská 12, Banská Bystrica, okres Banská Bystrica")
        self.assertTrue(o["description_raw"].startswith("Ponúkame zrekonštruované"))
        neg = c["Studio_01"]
        self.assertIsNone(neg["price"])
        self.assertEqual(neg["price_note"], "Info v RK")
        self.assertEqual(neg["area_m2"], 45.0)

    def test_page_validity(self):
        self.assertTrue(ns.page_is_for(fx.PAGE_OFFICES, "Banská Bystrica"))
        self.assertTrue(ns.page_is_for(fx.PAGE_EMPTY_NO_H1, "Banská Bystrica"))
        self.assertFalse(ns.page_is_for(fx.PAGE_GENERIC_REDIRECT, "Banská Bystrica"))
        self.assertEqual(ns.parse_page(fx.PAGE_EMPTY_NO_H1, "ine"), [])

    def test_location_in_city(self):
        self.assertTrue(ns.location_in_city("Kapitulská 12, Banská Bystrica, okres Banská Bystrica", "Banská Bystrica"))
        self.assertFalse(ns.location_in_city("Selce, okres Banská Bystrica", "Banská Bystrica"))   # obec z okresu
        self.assertTrue(ns.location_in_city(None, "Banská Bystrica"))

    def test_detail(self):
        d = ns.parse_detail(fx.DETAIL_OFFICE)
        self.assertEqual(d["area_m2"], 33.0)
        self.assertEqual(d["floor_label"], "3. poschodie (výťah)")
        self.assertEqual(d["ownership"], "Osobné")
        self.assertEqual(d["condition_label"], "Kompletná rekonštrukcia")
        self.assertIn("Cena prenájmu 265eur/mes + energie + DPH", d["description"])


def raw(pid="a", prop="kancelaria", price=300.0, area=40.0, title="Kancelária", desc="popis",
        location="Horná 5, Banská Bystrica, okres Banská Bystrica"):
    return {"source": "fake", "portal_id": pid, "url": f"https://x/{pid}", "title": title, "description_raw": desc,
            "prop_type": prop, "subtype": "Kancelárie, administratívne priestory", "location": location,
            "area_m2": area, "price": price, "price_note": None, "price_per_m2": None, "main_photo_url": None}


class FilterTests(unittest.TestCase):
    def test_reject(self):
        self.assertIsNone(scraper.rejection_reason(raw()))
        self.assertIsNone(scraper.rejection_reason(raw(price=None, area=None)))   # bez ceny/plochy sa neodmieta
        self.assertIn("iné mesto", scraper.rejection_reason(raw(location="Selce, okres Banská Bystrica")))
        self.assertIn("cena", scraper.rejection_reason(raw(price=config.PRICE_MAX + 1)))
        self.assertIn("pod", scraper.rejection_reason(raw(area=config.MIN_AREA_M2 - 1)))
        self.assertIn("nad", scraper.rejection_reason(raw(area=config.MAX_AREA_M2 + 1)))
        self.assertIn("dopyt", scraper.rejection_reason(raw(title="Hľadám kanceláriu")))
        self.assertIn("prenajaté", scraper.rejection_reason(raw(title="Prenajaté - kancelária")))

    def test_clear_implausible_prices_in_db(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.db")
            db.init_db(path)
            with db.connect(path) as conn:
                db.upsert_listing(conn, raw("a", price=1.0))
                db.upsert_listing(conn, raw("b", price=250.0))
                self.assertEqual(db.clear_implausible_prices(conn, config.MIN_PLAUSIBLE_PRICE), 1)
                self.assertIsNone(db.get_listing(conn, "fake:a")["price"])
                self.assertEqual(db.get_listing(conn, "fake:b")["price"], 250.0)
                self.assertEqual(db.get_price_history(conn, "fake:a"), [])
                self.assertEqual(db.clear_implausible_prices(conn, config.MIN_PLAUSIBLE_PRICE), 0)   # druhý beh: nič

    def test_implausible_price_becomes_none(self):
        # reálny prípad 27.9.2026: portál ukazuje "1 €/mes." pri viac-výmerovom inzeráte
        fixed = scraper.fix_implausible_price(raw(price=1.0))
        self.assertIsNone(fixed["price"])
        self.assertIn("neplausibiln", fixed["price_note"])
        self.assertIsNone(scraper.rejection_reason(fixed))          # bez ceny sa neodmieta
        self.assertEqual(scraper.fix_implausible_price(raw(price=250.0))["price"], 250.0)   # normálna cena ostáva
        self.assertIsNone(scraper.fix_implausible_price(raw(price=None))["price_note"])

    def test_real_listings_against_default_limits(self):
        cards = {x["portal_id"]: x for x in ns.parse_page(fx.PAGE_OFFICES, "kancelaria")}
        self.assertIsNone(scraper.rejection_reason(cards["Ju4gHY1H3_h"]))
        self.assertIsNone(scraper.rejection_reason(cards["Studio_01"]))
        self.assertIn("iné mesto", scraper.rejection_reason(cards["Village_1"]))
        big = ns.parse_page(fx.PAGE_SHOPS, "obchod")[0]
        self.assertIsNotNone(scraper.rejection_reason(big))   # 1007 m² aj 10 070 €/mes.
        areal = ns.parse_page(fx.PAGE_OTHER, "ine")[0]
        self.assertIn("plocha", scraper.rejection_reason(areal))


class PipelineTests(unittest.TestCase):
    DETAIL = {"area_m2": None, "floor_label": "prízemie", "ownership": "Osobné", "condition_label": "Novostavba",
              "description": "Priestor s výkladom. Nájom 300 € + energie ~80 € + DPH. Parkovanie pred budovou. " * 2}

    def run_once(self, conn, raws):
        mod = mock.Mock(SOURCE_NAME="fake", LABEL="Fake", spec=["SOURCE_NAME", "LABEL", "fetch_all", "fetch_detail"])
        mod.fetch_all = lambda: [dict(r) for r in raws]
        mod.fetch_detail = lambda url: dict(self.DETAIL)
        pending = []
        scraper.process_source(mod, conn, pending)
        return pending

    def test_seed_new_drop_and_price_none(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.db")
            db.init_db(path)
            with db.connect(path) as conn:
                self.assertEqual(self.run_once(conn, [raw("a", price=300)]), [])   # seed = ticho
                row = db.get_listing(conn, "fake:a")
                self.assertEqual(row["floor_label"], "prízemie")
                self.assertEqual(row["energy_included"], 0)
                self.assertEqual(row["vat"], 1)
                self.assertEqual(row["parking"], "included")
                self.assertIn("ground", row["flags"])
                p = self.run_once(conn, [raw("a", price=250), raw("b", price=None)])
                self.assertEqual(sorted(x["kind"] for x in p), ["new", "price_drop"])
                p = self.run_once(conn, [raw("a", price=None), raw("b", price=None)])   # 'Info v RK' -> cena ostane
                self.assertEqual(p, [])
                self.assertEqual(db.get_listing(conn, "fake:a")["price"], 250.0)
                p = self.run_once(conn, [raw("a", price=250), raw("b", price=400)])
                self.assertEqual([x["kind"] for x in p], ["price_set"])
                # inzerát mimo limitu sa vymaže
                self.run_once(conn, [raw("a", price=250), raw("b", price=9999)])
                self.assertIsNone(db.get_listing(conn, "fake:b"))


class NotifyTests(unittest.TestCase):
    def item(self, **kw):
        l = raw(); l.update({"flags": "studio", "floor_label": "prízemie", "energy_included": 0, "energy_extra": 80.0,
                             "vat": 1, "parking": "included", "price_per_m2": 7.5}); l.update(kw)
        return {"kind": "new", "listing": l, "old_price": None}

    def test_embed(self):
        e = notify.build_embed(self.item())
        d = e["description"]
        self.assertIn("300 €", d)
        self.assertIn("/mes.", d)
        self.assertIn("40 m²", d)
        self.assertIn("+ DPH", d)
        self.assertIn("+ energie (~80 €)", d)
        self.assertIn("Horná 5, Banská Bystrica", d)
        self.assertNotIn("okres", d)
        self.assertIn("štúdio", d)
        e = notify.build_embed({"kind": "price_drop", "listing": raw(price=250), "old_price": 300.0})
        self.assertIn("~~300 €~~", e["description"])
        e = notify.build_embed(self.item(price=None, price_note="Info v RK"))
        self.assertIn("Info v RK", e["description"])

    def test_kinds(self):
        self.assertEqual(notify.kind_for("price_changed", None, 500), "price_set")
        self.assertEqual(notify.kind_for("price_changed", 600, 500), "price_drop")
        self.assertIsNone(notify.kind_for("unchanged", 1, 1))

    def test_send(self):
        self.assertEqual(notify.SECRET_ENV, "DISCORD_WEBHOOK_STUDIO")
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch("notify.requests.post") as p:
            self.assertEqual(notify.send_notifications([self.item()]), 0)
            p.assert_not_called()
        ok = mock.Mock(status_code=204)
        with mock.patch("notify.requests.post", return_value=ok) as p, mock.patch("notify.time.sleep"):
            self.assertEqual(notify.send_notifications([self.item() for _ in range(20)], webhook="https://h/w"),
                             config.NOTIFY_MAX_PER_RUN)
            self.assertEqual(p.call_count, 3)
        limited = mock.Mock(status_code=429); limited.json.return_value = {"retry_after": 0.1}
        with mock.patch("notify.requests.post", side_effect=[limited, ok]), mock.patch("notify.time.sleep"):
            self.assertEqual(notify.send_notifications([self.item()], webhook="https://h/w"), 1)
        bad = mock.Mock(status_code=500)
        with mock.patch("notify.requests.post", return_value=bad), mock.patch("notify.time.sleep"):
            self.assertEqual(notify.send_notifications([self.item()], webhook="https://h/w"), 0)


class RenderTests(unittest.TestCase):
    def build(self, raws):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "t.db")
        db.init_db(path)
        with db.connect(path) as conn:
            for r in raws:
                db.upsert_listing(conn, scraper.enrich(r))
            db.record_source_run(conn, "fake", "ok", len(raws), None)
        return render.render(path, os.path.join(d, "index.html"))

    def test_render(self):
        html = self.build([raw("a", title="<script>alert(1)</script>", desc="Nájom + energie ~90 € + DPH"),
                           raw("b", prop="obchod", price=None), raw("c", prop="ine", price=500.0)])
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)
        for t in ("kancelaria", "obchod", "ine"):
            self.assertIn(f'data-type="{t}"', html)
        self.assertIn("Cena neuvedená", html)
        self.assertIn("studio-bb-favs", html)
        self.assertIn("fav-btn", html)
        self.assertIn("+ DPH", html)
        self.assertIn("spolu ~390 € /mes.", html)
        self.assertIn('data-filter="kancelaria"', html)
        self.assertNotIn("obec-btn\"", html.split("<script>")[1])   # žiadny zvyšok po obciach v JS

    def test_empty_db(self):
        self.assertIn("Žiadne inzeráty", self.build([]))


if __name__ == "__main__":
    unittest.main()
