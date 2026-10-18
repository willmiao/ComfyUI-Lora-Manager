"""Tests for the CivitAI model page price parser.

The fixture mirrors a real page payload; the cases that matter are the ones that
decide whether a user gets a price at all, and whether a lapsed gate is mistaken
for a live one.
"""

from pathlib import Path

import pytest

from py.utils.civitai_page_prices import MAX_PAGE_BYTES, parse_model_page_prices

FIXTURE = Path(__file__).parent / "fixtures" / "civitai_model_page_paid.html"


@pytest.fixture(scope="module")
def fixture_html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_parses_prices_for_gated_versions(fixture_html):
    prices = parse_model_page_prices(fixture_html)

    assert prices is not None
    # Lapsed gates and never-gated versions must not appear.
    assert set(prices) == {1001, 1002, 1003}


def test_permanent_gate_price(fixture_html):
    prices = parse_model_page_prices(fixture_html)
    permanent = prices[1001]

    assert permanent["price_buzz"] == 5000
    assert permanent["list_price_buzz"] == 5000
    assert permanent["generation_price_buzz"] == 100
    assert permanent["accepts_blue_buzz"] is False
    assert permanent["price_sale_ends_at"] is None


def test_timed_gate_uses_sale_price_as_effective(fixture_html):
    prices = parse_model_page_prices(fixture_html)
    timed = prices[1002]

    # The stored/list price stays visible for a strikethrough, the effective price
    # is what a buyer pays now.
    assert timed["price_buzz"] == 100
    assert timed["list_price_buzz"] == 125
    assert timed["accepts_blue_buzz"] is True
    assert timed["price_sale_ends_at"] == "2999-09-01T00:00:00.000Z"
    # Generation is bundled with the download tier here (`trialLimit` only).
    assert timed["generation_price_buzz"] is None


def test_timed_gate_without_recorded_end_is_still_priced(fixture_html):
    prices = parse_model_page_prices(fixture_html)

    assert prices[1003]["price_buzz"] == 300
    assert prices[1003]["generation_price_buzz"] is None


@pytest.mark.parametrize(
    "html",
    [
        None,
        "",
        "<html><body>no payload here</body></html>",
        '<script id="__NEXT_DATA__" type="application/json">{not json</script>',
        # Valid JSON, but not the shape we need.
        '<script id="__NEXT_DATA__" type="application/json">{"props":{}}</script>',
        # Model query present, but no versions.
        '<script id="__NEXT_DATA__" type="application/json">'
        '{"props":{"pageProps":{"trpcState":{"json":{"queries":['
        '{"queryKey":[["model","getById"]],"state":{"data":{}}}]}}}}}</script>',
    ],
)
def test_unusable_payloads_return_none(html):
    assert parse_model_page_prices(html) is None


def test_oversized_page_is_skipped():
    oversized = "x" * (MAX_PAGE_BYTES + 1)
    assert parse_model_page_prices(oversized) is None


def test_unrelated_first_query_does_not_win(fixture_html):
    """Query order varies per page; selection is by procedure name."""

    prices = parse_model_page_prices(fixture_html)
    assert prices is not None
    assert 1001 in prices
