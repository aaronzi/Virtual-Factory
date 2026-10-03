"""GS1 Digital Link resolver: links, content negotiation / linkType, linkset and the passport page."""

import json

from resolver.links import DEFAULT_LINK, GS1, VF, Urls, build_links, expand, linkset
from resolver.page import render
from resolver.server import handle
from resolver.service import Resolution
from vf_common.digital_link import DigitalLink

SERIAL = "PC3280-2026-000123"
DL = DigitalLink("04099999032808", SERIAL)
URLS = Urls(resolver="http://localhost:8096", dpp="http://localhost:8093")
CERT = "http://localhost:8091/submodels/x/submodel-elements/Documents%5B0%5D/attachment"
DPP = {
    "dppStatus": "Active",
    "https://admin-shell.io/idta/nameplate/3/0/Nameplate": {
        "ManufacturerProductDesignation": [{"language": "en", "value": "Profile cylinder"},
                                           {"language": "de", "value": "Profilzylinder"}],
        "ManufacturerProductType": "PC-32-80-DA-M", "SerialNumber": SERIAL},
    "https://admin-shell.io/idta/CarbonFootprint/CarbonFootprint/1/0": {"ProductCarbonFootprints": [
        {"LifeCyclePhases": ["A1-A3"], "PcfCO2eq": "4.32", "ReferenceImpactUnitForCalculation": "piece"}]},
    "0173-1#01-AHF578#003": {"Documents": [{
        "DocumentClassifications": [{"ClassId": "02-04"}],
        "DocumentVersions": [{"Title": [{"language": "en", "value": "Inspection certificate"}],
                              "DigitalFiles": [{"contentType": "application/pdf", "url": CERT}]}]}]},
    "https://virtual-factory.example/ids/smt/QualityInspection/1/0/Submodel": {"OverallResult": "Pass"},
}


class FakeResolver:
    urls = URLS

    def __init__(self, known=True):
        self.known = known

    def resolve(self, dl):
        if not self.known:
            return None
        links = build_links(dl, URLS, DPP, "http://localhost:8091/shells/abc",
                            "http://localhost:8091/shell-descriptors/abc")
        return Resolution(dl, dl.uri(), None, DPP, links)


def test_links_cover_passport_dpp_aas_and_certificate():
    links = {k.link_type: k for k in build_links(DL, URLS, DPP, "http://aas/shells/a", "http://reg/sd/a")}
    page = f"http://localhost:8096/passport/01/04099999032808/21/{SERIAL}"
    assert links[DEFAULT_LINK].href == page and links[GS1 + "pip"].href == page
    assert links[GS1 + "certificationInfo"].href == CERT
    assert links[VF + "dpp"].href.endswith("dppsByProductId/https%3A%2F%2Fvirtual-factory.example%2F01%2F"
                                           f"04099999032808%2F21%2F{SERIAL}")
    assert links[VF + "aas"].href == "http://aas/shells/a"
    assert expand("gs1:pip") == GS1 + "pip" and expand("https://x/y") == "https://x/y"


def test_default_request_redirects_to_the_passport_page_with_link_header():
    reply = handle(FakeResolver(), f"/01/04099999032808/21/{SERIAL}", "", {})
    assert reply.status == 307
    assert reply.headers["Location"].endswith(f"/passport/01/04099999032808/21/{SERIAL}")
    assert 'rel="linkset"' in reply.headers["Link"] and CERT in reply.headers["Link"]


def test_link_type_selects_the_target_and_falls_back_to_the_default_link():
    path = f"/01/04099999032808/21/{SERIAL}"
    assert handle(FakeResolver(), path, "linkType=gs1:certificationInfo", {}).headers["Location"] == CERT
    assert "/passport/" in handle(FakeResolver(), path, "linkType=gs1:recallStatus", {}).headers["Location"]


def test_linkset_by_accept_header_or_link_type():
    for query, headers in (("", {"accept": "application/linkset+json"}), ("linkType=linkset", {})):
        reply = handle(FakeResolver(), f"/01/04099999032808/21/{SERIAL}", query, headers)
        body = json.loads(reply.body)
        assert reply.status == 200 and reply.headers["Content-Type"] == "application/linkset+json"
        assert body["linkset"][0]["anchor"] == DL.uri()
        assert body["linkset"][0][GS1 + "certificationInfo"][0]["href"] == CERT


def test_errors_for_bad_gtin_and_unknown_items():
    assert handle(FakeResolver(), "/01/04099999032807", "", {}).status == 400
    assert handle(FakeResolver(known=False), f"/01/04099999032808/21/{SERIAL}", "", {}).status == 404
    assert handle(FakeResolver(), "/nothing", "", {}).status == 404
    assert json.loads(handle(FakeResolver(), "/.well-known/gs1resolver", "", {}).body)["supportedPrimaryKeys"]


def test_passport_page_in_both_languages_hides_restricted_content():
    res = FakeResolver().resolve(DL)
    en, de = render(res, "en", "http://x"), render(res, "de", "http://x")
    assert "Profile cylinder" in en and "4.32" in en and CERT in en and 'lang="en"' in en
    assert "Profilzylinder" in de and "Nur für berechtigte Akteure" in de and "Qualitätsprüfung" in de
    assert "Pass</" not in en  # the quality verdict itself is not shown
    path = f"/passport/01/04099999032808/21/{SERIAL}"
    reply = handle(FakeResolver(), path, "", {"accept-language": "de-DE"})
    assert reply.status == 200 and reply.headers["Content-Language"] == "de"


def test_linkset_groups_targets_by_link_type():
    links = build_links(DL, URLS, None, None, None)
    entry = linkset(DL.uri(), links)["linkset"][0]
    assert set(entry) == {"anchor", DEFAULT_LINK, GS1 + "pip", GS1 + "sustainabilityInfo"}


class SecuredResolver(FakeResolver):
    """Secure profile: restricted links (AAS, descriptor) need a bearer token of the realm (ADR-0027)."""
    token_url = "http://localhost:8180/realms/virtual-factory/protocol/openid-connect/token"

    def __init__(self):
        super().__init__()
        from vf_common.testing_tokens import verifier
        self.verifier = verifier()

    def resolve(self, dl):
        links = build_links(dl, URLS, DPP, "http://localhost:8091/shells/abc",
                            "http://localhost:8091/shell-descriptors/abc", protect=True)
        return Resolution(dl, dl.uri(), None, DPP, links)


def test_restricted_link_types_need_a_token_in_the_secure_profile():
    from vf_common.testing_tokens import token
    path = f"/01/04099999032808/21/{SERIAL}"
    refused = handle(SecuredResolver(), path, "linkType=vf:aas", {})
    hint = json.loads(refused.body)
    assert refused.status == 401 and "Bearer" in refused.headers["WWW-Authenticate"]
    assert hint["login"]["token_endpoint"].endswith("/token")
    ok = handle(SecuredResolver(), path, "linkType=vf:aas", {"authorization": "Bearer " + token(["auditor"])})
    assert ok.status == 307 and ok.headers["Location"] == "http://localhost:8091/shells/abc"
    assert handle(SecuredResolver(), path, "linkType=vf:dpp", {}).status == 307  # DPP API filters by role
    page = render(SecuredResolver().resolve(DL), "en", "http://x")
    assert "login required" in page


def test_passport_page_names_sections_withheld_from_the_public_role():
    material = "https://virtual-factory.example/ids/smt/ProductMaterialComposition/1/0/Submodel"
    dpp = {**DPP, "contentSpecificationIds": [material]}
    res = Resolution(DL, DL.uri(), None, dpp, build_links(DL, URLS, dpp, None, None))
    html = render(res, "en", "http://x")
    assert "For authorised parties only" in html and "Material composition" in html
    assert 'id="materials"' not in html
