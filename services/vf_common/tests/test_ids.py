from vf_common import ids


def test_id_scheme():
    assert ids.aas_id("CV01") == "https://virtual-factory.example/ids/aas/CV01"
    assert ids.submodel_id("CV01", "Nameplate", "3") == (
        "https://virtual-factory.example/ids/sm/CV01/Nameplate/3")
    assert ids.serial_number(2026, 123) == "PC3280-2026-000123"
