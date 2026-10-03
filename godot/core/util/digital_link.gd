class_name DigitalLink
extends RefCounted
## GS1 Digital Link URIs (ADR-0021, ADR-0023): `<domain>/01/<GTIN-14>[/21/<serial>]`. The canonical URI is
## the product's globalAssetId and the content of its QR code; a scanner app re-bases the path onto the
## resolver it is configured with (the domain is not significant for the identification).

const DEFAULT_DOMAIN := "https://virtual-factory.example"


static func item(gtin: String, serial: String, domain := DEFAULT_DOMAIN) -> String:
	return "%s/01/%s/21/%s" % [domain.trim_suffix("/"), gtin, serial.uri_encode()]


static func product(gtin: String, domain := DEFAULT_DOMAIN) -> String:
	return "%s/01/%s" % [domain.trim_suffix("/"), gtin]


## Path part `/01/...` of a Digital Link URI, "" if the URI is none.
static func path_of(uri: String) -> String:
	var start := uri.find("/01/")
	return uri.substr(start) if start >= 0 else ""


## The same Digital Link on another resolver; "" if `uri` is not a Digital Link.
static func rebase(uri: String, resolver_url: String) -> String:
	var path := path_of(uri)
	return resolver_url.trim_suffix("/") + path if path != "" else ""


## Serial (AI 21) of an item Digital Link, "" for a product link.
static func serial_of(uri: String) -> String:
	var start := uri.find("/21/")
	return uri.substr(start + 4).uri_decode() if start >= 0 else ""
