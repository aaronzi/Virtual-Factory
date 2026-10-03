extends GutTest
## GS1 Digital Link helpers: canonical URIs and re-basing onto a resolver.


func test_item_and_product_links() -> void:
	var item := DigitalLink.item("04099999032808", "PC3280-2026-000123")
	assert_eq(item, "https://virtual-factory.example/01/04099999032808/21/PC3280-2026-000123")
	assert_eq(DigitalLink.product("04099999032808"), "https://virtual-factory.example/01/04099999032808")
	assert_eq(DigitalLink.rebase(item, "http://localhost:8096/"),
		"http://localhost:8096/01/04099999032808/21/PC3280-2026-000123")
	assert_eq(DigitalLink.serial_of(item), "PC3280-2026-000123")
	assert_eq(DigitalLink.rebase("https://virtual-factory.example/ids/asset/CV01", "http://x"), "")
