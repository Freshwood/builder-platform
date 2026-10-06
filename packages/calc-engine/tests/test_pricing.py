from datetime import UTC, datetime
from decimal import Decimal

from calc_engine.assembly.templates import templates
from calc_engine.catalog import search_query
from calc_engine.engine import default_engine
from construction_model.model import ProjectInputs

engine = default_engine(clock=lambda: datetime(2026, 10, 6, tzinfo=UTC))


def shutter(prices: dict[str, Decimal] | None = None) -> ProjectInputs:
    return ProjectInputs(
        title="Laden",
        pack_id="design",
        params={"width_mm": 310, "height_mm": 380},
        design=templates()["window_shutter"].design,
        prices=prices or {},
    )


def test_opened_packs_count_pro_rata_in_used_cost() -> None:
    r = engine.build(shutter())
    screws = next(line for line in r.bom if line.item_id.startswith("screw_"))
    assert screws.used_share is not None
    assert screws.used_share < Decimal("0.2")
    used = r.costs.material_used
    assert used is not None
    # A small shutter uses only a fraction of a screw pack and an oil can.
    assert used.max < r.costs.material.max * Decimal("0.7")
    assert r.costs.user_priced == 0
    assert all(line.price_source == "estimate" for line in r.bom)


def test_user_price_replaces_guide_price_everywhere() -> None:
    before = engine.build(shutter())
    oil = next(line for line in before.bom if line.item_id.startswith("finish_"))
    after = engine.build(shutter({oil.item_id: Decimal("9.99")}))
    line = next(line for line in after.bom if line.item_id == oil.item_id)
    assert line.price_source == "user"
    assert line.unit_price.min == line.unit_price.max == Decimal("9.99")
    assert after.costs.user_priced == 1
    assert after.costs.material.min == before.costs.material.min - oil.total.min + Decimal("9.99")
    # Variants are priced with the same user prices.
    for variant, old in zip(after.variants, before.variants, strict=True):
        assert variant.material_cost.max < old.material_cost.max


def test_unknown_price_keys_are_ignored() -> None:
    assert engine.build(shutter({"nothing": Decimal(1)})).costs.user_priced == 0


def test_search_query_is_short_and_keeps_decimal_commas() -> None:
    assert search_query("Holzöl außen für Douglasie/Lärche", "0,75 l, ca. 9 m² je Anstrich") == (
        "Holzöl außen für Douglasie/Lärche 0,75 l"
    )
    assert search_query("Spanplattenschraube verzinkt, Senkkopf", "4 × 30 mm, Packung 200 Stk") == (
        "Spanplattenschraube verzinkt 4 × 30 mm"
    )
    assert search_query("Brett Douglasie, gehobelt", "18 × 98 mm, Länge 5,00 m") == (
        "Brett Douglasie 18 × 98 mm"
    )
