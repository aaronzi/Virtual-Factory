"""GS1 Digital Link parsing, check digits and re-basing onto a resolver."""

import pytest

from vf_common.digital_link import (DigitalLink, InvalidDigitalLink, batch_link, gtin_check_digit, parse,
                                   parse_path)


def test_check_digit_of_the_product_gtin():
    assert gtin_check_digit("0409999903280") == 8
    assert gtin_check_digit("400638133393") == 1  # GS1 example GTIN-13 4006381333931


def test_parse_item_and_product_links_with_any_domain():
    item = parse("https://virtual-factory.example/01/04099999032808/21/PC3280-2026-000123")
    assert item == DigitalLink("04099999032808", "PC3280-2026-000123")
    assert parse("http://localhost:8096/01/4099999032808") == DigitalLink("04099999032808")  # GTIN-13 padded
    assert item.uri() == "https://virtual-factory.example/01/04099999032808/21/PC3280-2026-000123"
    assert item.rebase("http://localhost:8096/") == \
        "http://localhost:8096/01/04099999032808/21/PC3280-2026-000123"
    assert item.product == DigitalLink("04099999032808")


@pytest.mark.parametrize("path", ["/01/04099999032807", "/01/abc", "/02/04099999032808",
                                  "/01/04099999032808/22/x"])
def test_invalid_paths_are_rejected(path):
    with pytest.raises(InvalidDigitalLink):
        parse_path(path)


def test_batch_links_of_supplier_lots():
    link = batch_link("04099991010019", "DGP-260914-F")
    assert link == "https://virtual-factory.example/01/04099991010019/10/DGP-260914-F"
    assert parse(link) == DigitalLink("04099991010019", lot="DGP-260914-F")
    assert parse_path("/01/04099991010019/10/L1/21/S1") == DigitalLink("04099991010019", "S1", "L1")
