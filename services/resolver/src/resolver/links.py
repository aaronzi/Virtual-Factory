"""Links of a product or item Digital Link (GS1 Web Vocabulary link types + Virtual Factory link types) and
their RFC 9264 linkset representation as GS1-conformant resolvers serve it."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from urllib.parse import quote

from vf_common.basyx import b64
from vf_common.digital_link import DigitalLink

GS1 = "https://gs1.org/voc/"
VF = "https://virtual-factory.example/voc/"
PREFIXES = {"gs1:": GS1, "vf:": VF}
DEFAULT_LINK = GS1 + "defaultLink"
PIP = GS1 + "pip"
HANDOVER = "0173-1#01-AHF578#003"
DOCUMENT_LINK_TYPES = {"02-04": GS1 + "certificationInfo", "03-01": GS1 + "instructions",
                       "03-05": GS1 + "instructions"}
# targets that need a token of the realm in the secure profile (ADR-0027); the DPP API is role-filtered itself
PROTECTED_LINK_TYPES = (VF + "aas", VF + "aasDescriptor")


@dataclass(frozen=True)
class Urls:
    """Public base URLs written into links (what a browser on the host can reach)."""
    resolver: str
    dpp: str


@dataclass(frozen=True)
class Link:
    link_type: str                  # full URI
    href: str
    title: dict[str, str]           # language -> title
    media_type: str = "text/html"
    hreflang: tuple[str, ...] = field(default=())
    restricted: bool = False        # secure profile: the resolver redirects only with a valid bearer token

    def as_target(self, lang: str = "en") -> dict:
        target = {"href": self.href, "title": self.title.get(lang) or next(iter(self.title.values()), ""),
                  "type": self.media_type}
        if self.hreflang:
            target["hreflang"] = list(self.hreflang)
        return target


def expand(link_type: str) -> str:
    """CURIE (gs1:pip, vf:dpp) or full URI -> full URI."""
    for prefix, base in PREFIXES.items():
        if link_type.startswith(prefix):
            return base + link_type[len(prefix):]
    return link_type


def build_links(dl: DigitalLink, urls: Urls, dpp: dict | None, shell_href: str | None,
                descriptor_url: str | None, protect: bool = False) -> list[Link]:
    """All links of a resolved Digital Link; the passport page is the default link. protect: mark the links to
    restricted data (PROTECTED_LINK_TYPES) as restricted (secure profile)."""
    page = f"{urls.resolver.rstrip('/')}/passport{dl.path}"
    both = ("en", "de")
    links = [Link(DEFAULT_LINK, page, {"en": "Digital product passport", "de": "Digitaler Produktpass"},
                  hreflang=both),
             Link(PIP, page, {"en": "Product information page (passport)",
                              "de": "Produktinformationsseite (Produktpass)"}, hreflang=both),
             Link(GS1 + "sustainabilityInfo", page + "#sustainability",
                  {"en": "Carbon footprint and circularity", "de": "CO2-Fußabdruck und Kreislauffähigkeit"},
                  hreflang=both)]
    if dpp is not None:
        dpp_url = f"{urls.dpp.rstrip('/')}/v1/dppsByProductId/{quote(dl.uri(), safe='')}"
        links.append(Link(VF + "dpp", dpp_url, {"en": "Digital product passport (DPP API, JSON)",
                                                "de": "Produktpass (DPP-API, JSON)"}, "application/json"))
        links += document_links(dpp)
    if shell_href:
        links.append(Link(VF + "aas", shell_href, {"en": "Asset Administration Shell",
                                                  "de": "Verwaltungsschale"}, "application/json"))
    if descriptor_url:
        links.append(Link(VF + "aasDescriptor", descriptor_url,
                          {"en": "AAS descriptor (registry)", "de": "VWS-Deskriptor (Registry)"},
                          "application/json"))
    if protect:
        links = [replace(k, restricted=True) if k.link_type in PROTECTED_LINK_TYPES else k for k in links]
    return links


def document_links(dpp: dict) -> list[Link]:
    """Certificates and instructions of the HandoverDocumentation section (VDI 2770 class -> link type)."""
    out = []
    for doc in (dpp.get(HANDOVER) or {}).get("Documents") or []:
        link_type = DOCUMENT_LINK_TYPES.get(_class_id(doc))
        version = (doc.get("DocumentVersions") or [{}])[0]
        files = [f for f in version.get("DigitalFiles") or [] if isinstance(f, dict) and f.get("url")]
        if link_type and files:
            titles = {t["language"]: t["value"] for t in version.get("Title") or []}
            media_type = files[0].get("contentType", "application/pdf")
            languages = tuple(version.get("Language") or ())
            out.append(Link(link_type, files[0]["url"], titles, media_type, languages))
    return out


def linkset(anchor: str, links: list[Link], lang: str = "en") -> dict:
    """RFC 9264 linkset (application/linkset+json) with link types as relation keys."""
    entry: dict = {"anchor": anchor}
    for link in links:
        entry.setdefault(link.link_type, []).append(link.as_target(lang))
    return {"linkset": [entry]}


def link_header(self_url: str, links: list[Link]) -> str:
    """HTTP Link header: the linkset itself plus every link (GS1 resolver behaviour)."""
    parts = [f'<{self_url}?linkType=linkset>; rel="linkset"; type="application/linkset+json"']
    parts += [f'<{link.href}>; rel="{link.link_type}"; type="{link.media_type}"' for link in links
              if link.link_type != DEFAULT_LINK]
    return ", ".join(parts)


def descriptor_url(registry_public: str, aas_id: str) -> str:
    return f"{registry_public.rstrip('/')}/shell-descriptors/{b64(aas_id)}"


def _class_id(doc: dict) -> str:
    classes = doc.get("DocumentClassifications") or [{}]
    return str(classes[0].get("ClassId", ""))
