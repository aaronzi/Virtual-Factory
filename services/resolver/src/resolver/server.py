"""HTTP interface of the GS1 Digital Link resolver (GS1-Conformant Resolver behaviour, simplified):

    GET /01/{gtin}[/21/{serial}]            307 -> default link (passport page), Link header with all links
        ?linkType=gs1:pip | vf:dpp | ...    307 -> first link of that type (default link if there is none)
        ?linkType=linkset|all  or  Accept: application/linkset+json   200 linkset (RFC 9264)
    GET /passport/01/{gtin}[/21/{serial}]   human-readable passport page (?lang=en|de, else Accept-Language)
    GET /.well-known/gs1resolver            resolver description;  GET /health
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from vf_common.digital_link import InvalidDigitalLink, parse_path

from . import page
from .links import DEFAULT_LINK, GS1, VF, expand, link_header, linkset
from .service import DigitalLinkResolver

log = logging.getLogger("resolver")
LINKSET = "application/linkset+json"


@dataclass
class Reply:
    status: int
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)


def handle(resolver: DigitalLinkResolver, path: str, query: str, headers: dict[str, str]) -> Reply:
    params = {k: v[0] for k, v in parse_qs(query).items()}
    if path == "/health":
        return _json(200, {"status": "ok"})
    if path == "/.well-known/gs1resolver":
        return _json(200, description(resolver))
    passport = path.startswith("/passport/")
    try:
        dl = parse_path(path.removeprefix("/passport"))
    except InvalidDigitalLink as exc:
        return _json(400 if path.startswith(("/01/", "/passport/01/")) else 404, {"error": str(exc)})
    res = resolver.resolve(dl)
    if res is None:
        return _json(404, {"error": f"unknown product / item {dl.uri()}"})
    lang = _language(params, headers)
    self_url = resolver.urls.resolver.rstrip("/") + path
    if passport:
        html = page.render(res, lang, self_url).encode()
        return Reply(200, html, {"Content-Type": "text/html; charset=utf-8", "Content-Language": lang})
    vary = {"Vary": "Accept, Accept-Language", "Link": link_header(self_url, res.links)}
    link_type = params.get("linkType", "")
    if link_type in ("linkset", "all") or (not link_type and _wants_linkset(headers.get("accept", ""))):
        return Reply(200, json.dumps(linkset(res.anchor, res.links, lang), ensure_ascii=False).encode(),
                     {"Content-Type": LINKSET, **vary})
    target = (res.link(expand(link_type)) if link_type else None) or res.link(DEFAULT_LINK)
    return Reply(307, b"", {"Location": target.href, **vary})


def description(resolver: DigitalLinkResolver) -> dict:
    return {"name": "Virtual Factory GS1 Digital Link resolver", "resolverRoot": resolver.urls.resolver,
            "supportedPrimaryKeys": ["01"], "supportedQualifiers": ["21"],
            "linkTypeDefaultCanBeLinkset": False,
            "supportedLinkTypes": [GS1 + t for t in ("defaultLink", "pip", "sustainabilityInfo",
                                                     "certificationInfo", "instructions")]
            + [VF + t for t in ("dpp", "aas", "aasDescriptor")]}


def _wants_linkset(accept: str) -> bool:
    accept = accept.lower()
    return LINKSET in accept or ("application/json" in accept and "text/html" not in accept)


def _language(params: dict, headers: dict[str, str]) -> str:
    lang = params.get("lang") or headers.get("accept-language", "en")[:2]
    return "de" if lang.lower() == "de" else "en"


def _json(status: int, body: dict) -> Reply:
    return Reply(status, json.dumps(body).encode(), {"Content-Type": "application/json"})


def serve(resolver: DigitalLinkResolver, port: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - http.server API
            url = urlsplit(self.path)
            reply = handle(resolver, url.path, url.query, {k.lower(): v for k, v in self.headers.items()})
            self.send_response(reply.status)
            for key, value in {"Access-Control-Allow-Origin": "*", **reply.headers}.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(reply.body)))
            self.end_headers()
            self.wfile.write(reply.body)

        def log_message(self, fmt, *args):
            log.debug(fmt, *args)

    return ThreadingHTTPServer(("", port), Handler)
