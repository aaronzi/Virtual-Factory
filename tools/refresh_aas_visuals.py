#!/usr/bin/env python3
"""Refresh static AAS visuals without re-provisioning operational data or workpiece passports.

Dry run by default. --apply uploads only generated thumbnails, visual File attachments, and Models3D
version/date properties, then reads back every upload. Uses the normal service-auth environment if set.
"""

import argparse

from provisioner.build import REPO, build
from vf_common.aas.aasx import _thumbnail
from vf_common.basyx import BasyxClient, b64


def elements(node: dict, path: str = ""):
    """Walk API idShort paths, including index-addressed SubmodelElementLists."""
    yield path, node
    kind = node.get("modelType")
    children = node.get("submodelElements", []) if kind == "Submodel" else node.get("value", [])
    if kind not in {"Submodel", "SubmodelElementCollection", "SubmodelElementList"}:
        return
    for index, child in enumerate(children):
        suffix = f"[{index}]" if kind == "SubmodelElementList" else child["idShort"]
        child_path = path + suffix if suffix.startswith("[") else ".".join(filter(None, [path, suffix]))
        yield from elements(child, child_path)


def is_visual(source: str) -> bool:
    return source.startswith("docs/screenshots/assets/") or source == "docs/screenshots/factory-line.png" \
        or (source.startswith("godot/") and source.endswith(".glb"))


def visual_jobs(result) -> list[dict]:
    jobs = []
    files = result.builder.files
    thumbnails = set()
    for shell in result.environment["assetAdministrationShells"]:
        package = shell["assetInformation"].get("defaultThumbnail", {}).get("path")
        if package and is_visual(files.get(package, "")):
            thumbnails.add(package)
            jobs.append({"url": f"/shells/{b64(shell['id'])}/asset-information/thumbnail",
                         "source": files[package], "thumbnail": True, "mime": "image/png"})
    for sm in result.environment["submodels"]:
        for path, element in elements(sm):
            source = files.get(element.get("value", ""), "") if element["modelType"] == "File" else ""
            url = f"/submodels/{b64(sm['id'])}/submodel-elements/{path}"
            if is_visual(source):
                jobs.append({"url": url + "/attachment", "source": source,
                             "thumbnail": element["value"] in thumbnails, "mime": element["contentType"]})
            if sm["idShort"] == "Models3D" and element.get("idShort") in {"FileVersionId", "SetDate"}:
                jobs.append({"url": url + "/$value", "value": element["value"]})
    return jobs


def apply_job(client: BasyxClient, job: dict) -> None:
    url = job["url"]
    if "source" in job:
        source = REPO / job["source"]
        data = _thumbnail(source).getvalue() if job["thumbnail"] else source.read_bytes()
        response = client.http.put(url, files={"file": (source.name, data, job["mime"])},
                                   data={"fileName": source.name})
        response.raise_for_status()
        fetched = client.http.get(url)
        fetched.raise_for_status()
        if fetched.content != data:
            raise RuntimeError(f"Uploaded bytes do not match: {job['source']}")
    else:
        response = client.http.patch(url, json=job["value"])
        response.raise_for_status()
        fetched = client.http.get(url)
        fetched.raise_for_status()
        if fetched.json() != job["value"]:
            raise RuntimeError(f"Version metadata did not round-trip: {url}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8091")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    jobs = visual_jobs(build())
    client = BasyxClient(args.url)
    try:
        for job in jobs:
            print(job.get("source", job.get("value")), "->", job["url"])
            if args.apply:
                apply_job(client, job)
    finally:
        client.http.close()
    print(f"{len(jobs)} visual updates {'applied and verified' if args.apply else 'planned (dry run)'}")


if __name__ == "__main__":
    main()
