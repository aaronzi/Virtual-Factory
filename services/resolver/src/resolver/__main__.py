"""Entry point: python -m resolver (configuration via environment variables, docs/interfaces/services.md)."""

from __future__ import annotations

import logging
import os

from vf_common.resolver import AasResolver

from .links import Urls
from .server import serve
from .service import DigitalLinkResolver


def main() -> None:
    env = os.environ.get
    logging.basicConfig(level=env("LOG_LEVEL", "INFO"), format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    port = int(env("VF_RESOLVER_PORT", "8096"))
    urls = Urls(resolver=env("VF_RESOLVER_PUBLIC_URL", f"http://localhost:{port}"),
                dpp=env("VF_DPP_PUBLIC_URL", "http://localhost:8093"))
    resolver = DigitalLinkResolver(AasResolver.from_env(), env("VF_DPP_URL", "http://localhost:8093"), urls)
    logging.getLogger("resolver").info("GS1 Digital Link resolver on :%d (public %s)", port, urls.resolver)
    serve(resolver, port).serve_forever()


if __name__ == "__main__":
    main()
