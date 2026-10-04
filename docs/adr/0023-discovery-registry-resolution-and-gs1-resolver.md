# ADR-0023: AAS resolution via discovery and registry; GS1 Digital Link resolver and QR codes on the parts

- Status: accepted
- Date: 2026-10-03
- Extends: [ADR-0004](0004-ephemeral-instances-preloaded-static-aas.md), [ADR-0018](0018-in-world-training-ui.md),
  [ADR-0021](0021-item-level-dpp-basyx-dpp-api.md)

## Context

All clients (bridge, MES, ops gateway, Godot inspector) built AAS and submodel ids from the id scheme
(`vf_common.ids.aas_id(tag)`, `submodel_id(tag, idShort, version)`, `AasClient.aas_id`) and called the AAS
repository at one fixed URL. Real deployments do not work like that. A client knows an **asset id** (globalAssetId
on the type plate, a serial number, a GS1 Digital Link in a QR code). It asks a **discovery service** for the AAS
id and the **registry** for the descriptor, then calls the endpoint in the descriptor, which can be in another
company's environment. The products already carry GS1 Digital Links as globalAssetId (ADR-0021), but nothing
resolved them, and the part model showed a fake data matrix.

Facts verified on the running BaSyx Go AAS environment 1.1.0 (port 8091):

- `/lookup/shells?assetIds=<base64url({"name","value"})>` (discovery) is populated from the shells, including
  specific asset ids (`serialNumber`, `manufacturerPartId`); several `assetIds` must all match.
- `GENERAL_AASREGISTRYINTEGRATION` / `GENERAL_SUBMODELREGISTRYINTEGRATION` register every shell and submodel,
  also the workpiece AAS the MES creates. Descriptor endpoints are `GENERAL_EXTERNALURL` + `/shells/<b64>` or
  `/submodels/<b64>` (`http://localhost:8091/...`, interfaces `AAS-3.2` / `SUBMODEL-3.2`).
- The `submodelDescriptors` inside a shell descriptor carry only id and endpoint. idShort and semanticId are in
  the submodel registry (`/submodel-descriptors/<b64>`).
- The DPP API (8093) finds an item passport by product id = globalAssetId (`/v1/dppsByProductId/<DL>`).

## Decision

**Resolution chain in all clients.** `vf_common.resolver.AasResolver` implements
asset id → discovery → AAS id → AAS registry → shell endpoint, submodel ids → submodel registry → idShort,
semanticId, endpoint → repository client for that endpoint.

- `RegistryConfig` lists **several environments** (`VF_AAS_REGISTRIES`: `name=base,...` or a JSON list with
  separate discovery / AAS registry / submodel registry URLs). The first environment that knows an id wins, so a
  supplier's environment can be added without code changes. `VF_AAS_ENDPOINT_MAP` rewrites public descriptor URLs
  to reachable ones (in compose: `http://localhost:8091` → `http://aas-env:8091`). By default it is derived from
  `VF_AAS_PUBLIC_URL` → `VF_AAS_URL`. Authentication is an injectable `httpx.Auth`, ready for the Keycloak phase.
- Positive results are cached (`VF_AAS_RESOLVER_TTL`, 300 s). BaSyx change events invalidate entries early: shell
  created/updated/deleted, submodel created/deleted. Submodel value updates do not change endpoints and are
  ignored.
- `vf_common.registry_aas.RegistryAas` is the read/write surface of `BasyxClient` (`AasSource`) on top of the
  resolver: `get_shell`, `get_submodel`, `list_submodels(semanticId)` (submodel registry scan), `get_value`,
  `set_value`, `invoke`, each routed to the repository named in the descriptor.
- Use per service. The **bridge** finds the AIMC/AID submodels in the submodel registry and writes sinks through
  the registry. The **ops gateway** resolves `LineControl` from the line's asset id (`VF_LINE_ASSET_ID`, default
  `…/ids/asset/LINE01`) and reads the Control Component and AID through the registry. The **MES** reads the AID
  events, LineControl and PLC01 OperationalData through the registry, and takes the thumbnail link of workpieces
  from the descriptor endpoint of the product type (resolved by its GTIN Digital Link). A service still writes
  the AAS it **owns** (workpieces, KLT contents, KPI submodel; the provisioner's preload) into its own
  repository; the repository's registry integration registers them. The historian does not use the AAS.
- **Godot**: `AasClient.lookup` (discovery) and `describe` (registry) cache the shell and submodel endpoints;
  `get_shell`, `get_submodel(s)`, `get_thumbnail` and `invoke` use these hrefs. The inspector opens an asset by
  its **global asset id**. A workpiece reports the Digital Link of its QR code (`TrackedItem.get_asset_id()`).
  Devices and props use their asset id `…/ids/asset/<tag>`, i.e. the id on their type plate (an asset id, not an
  AAS id). `backend.json` `aas_registries` lists the environments.
- **Fallback.** An id that no registry knows is read from the own repository (`aas_url`) by its id, nothing more.
  The id scheme of `vf_common.ids` stays the way ids are **minted** (provisioner, MES) and the way device asset ids
  are written. Concept descriptions have no registry and are read from the own repository.

**GS1 Digital Link resolver** (`services/resolver`, compose `resolver`, port 8096, stdlib HTTP server):

- `GET /01/{gtin}[/21/{serial}]`: the GTIN check digit is validated. The resolver looks up the canonical URI
  (`https://virtual-factory.example/01/…`) as globalAssetId in discovery/registry and in the DPP API. It answers
  307 to the default link (passport page) with a `Link` header that lists all links. `?linkType=<CURIE or URI>`
  selects a link and falls back to the default link. `?linkType=linkset|all` or `Accept: application/linkset+json`
  returns an RFC 9264 linkset. Unknown items get 404, malformed links 400.
- Link types: `gs1:defaultLink`, `gs1:pip` and `gs1:sustainabilityInfo` (passport page); `gs1:certificationInfo`
  (inspection certificate, REACH information) and `gs1:instructions` (operating and repair instructions) come
  from the HandoverDocumentation (VDI 2770 classes 02-04, 03-01, 03-05); `vf:dpp` (DPP API by product id),
  `vf:aas` (shell endpoint) and `vf:aasDescriptor` (registry descriptor), with
  `vf:` = `https://virtual-factory.example/voc/`.
- Passport page `GET /passport/01/…` (en/de by `?lang` or `Accept-Language`) renders the **public** sections of
  the compressed DPP: nameplate, PCF, material composition, circularity, contacts, documents. Technical data, BoM,
  executed processes and quality are only named as "for authorised parties". Access control follows in the
  security phase.
- **Host mapping.** `.example` is a reserved TLD (RFC 2606) and never resolves. The QR code encodes the
  **canonical** Digital Link; the identifier stays unchanged. A scanner app (here: the inspector action) moves the
  path onto the resolver it is configured with (`resolver_url`), as GS1 resolvers allow. No hosts entry or proxy
  is needed.

**QR code on the part.** `core/util/qr_code.gd` (+ layout, penalty, Reed-Solomon) is a self-written ISO/IEC
18004 encoder: byte mode, level M, versions 1-10, automatic mask. It is tested against reference vectors of
Nayuki's qrcodegen and the RS example of ISO/IEC 18004 Annex I. The cylinder's type plate surface gets a shader
material (`label_qr.gdshader`): the shared label texture plus a per-part 45×45 L8 QR texture (nearest filtering)
in a square area that covers the former fake data matrix. Encoding (≈13 ms) runs on the WorkerThreadPool. Until
it is done, the label shows the QR of the product type. The inspector action *Scan QR code (open passport)*
opens the resolver URL of the workpiece's globalAssetId and replaces *Open passport (DPP API)*.

## Consequences

- No client builds AAS or submodel ids for reading. The same code reads AAS from a second environment once it is
  listed in `VF_AAS_REGISTRIES` / `aas_registries`. Its endpoints must be reachable or mapped.
- First access per AAS costs one discovery call plus one registry call per AAS and submodel (cached afterwards).
  The bridge resolves its ~10 AIMC and ~20 referenced submodels at start-up; value writes then go straight to the
  cached endpoint.
- The draw-call budget is unchanged: the QR uses the existing label surface, and the label is now opaque instead
  of the imported depth-prepass material. Measured with full KLTs, 450 (452 with one more part in view) both with
  and without the QR (`--vf-perf-report=5 --vf-perf-warmup=170`).
- The default resolver links point to `localhost` (public URLs of the compose stack); other hosts set
  `VF_RESOLVER_PUBLIC_URL`, `VF_DPP_PUBLIC_URL`, `VF_AAS_PUBLIC_URL`.
- Open issues: O45 (registry scan for semanticId queries), O46 (passport access levels without auth), O47
  (resolver data only from the own environment's DPP API).
