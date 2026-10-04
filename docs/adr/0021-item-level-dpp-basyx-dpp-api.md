# ADR-0021: Item-level digital product passports served by the BaSyx Go DPP API

- Status: accepted
- Date: 2026-10-03
- Extends: [ADR-0004](0004-ephemeral-instances-preloaded-static-aas.md), [ADR-0011](0011-template-based-aas-generation.md),
  [ADR-0016](0016-bpmn-orchestration.md)

## Context

The workpiece instance AAS created by the MES carried only a thin passport: Nameplate, DppMetadata, actual PCF,
production log and quality data. Documents, contacts, as-built technical data, traceability, material composition
and circularity existed only on the product type. The DppMetadata id (`…/dpp/item/<serial>`) differed from the AAS
id. The user wants to add the **BaSyx Go DPP API** (`eclipsebasyx/dppapi-go:1.1.0`) and fetch the passport of a
produced part through it.

Facts from the DPP API source (v1.1.0), verified against the running stack:

- It reads passports straight from the AAS database (same PostgreSQL as the AAS environment).
- `GET /v1/dpps/{dppId}` loads the AAS with id = dppId and needs `DppMetadata.digitalProductPassportId` = dppId,
  otherwise 404 (documented BaSyx limitation; the DPP specification allows different ids).
- `GET /v1/dppsByProductId/{productId}` matches the **AAS `globalAssetId`** (not `uniqueProductIdentifier`).
  With the old ids the lookup by GS1 Digital Link returned 404, the lookup by `…/ids/asset/WP_…` worked.
- Content sections = the AAS's submodels whose (last) semanticId key is listed in `contentSpecificationIds`. Only
  one submodel per semanticId is shown (the newest).
- Managed File attachments are rendered as links `{GENERAL_EXTERNALURL}/submodels/{id}/submodel-elements/{path}/attachment`.

## Decision

**Ids.** DPP id = AAS id (`https://virtual-factory.example/ids/aas/WP_<serial>`). We keep the AAS id scheme of
`vf_common.ids` and do not switch the AAS id to a `/dpp/...` URL. Godot, the store, KLT contents and references
all address workpieces by AAS id. A second id kind for the same object would only add a mapping. The product id
stays the GS1 Digital Link (`https://virtual-factory.example/01/04099999032808/21/<serial>`). It becomes both
`uniqueProductIdentifier` and the **globalAssetId** of the workpiece. That is what the DPP API builds itself on
create, and it is the usual choice for product instances. The asset data format gets an optional
`globalAssetId` (default `ids.asset_id(tag)`), which `${asset:TAG}` also resolves. The product type follows the
same rule (model-level passport: DPP id = type AAS id, globalAssetId = GTIN Digital Link
`…/01/04099999032808`). KLT content nodes reference the workpiece's Digital Link.

**Self-contained item-level passport.** Every part gets its own submodels (derivedFrom the type remains):

| Submodel | Content | Stage |
|---|---|---|
| Nameplate, ContactInformations | manufacturer, after-sales service, take-back/recycling contact | released |
| HierarchicalStructures 1.1 | as-built BoM: type BoM with the component batch per node | released |
| ProductMaterialComposition, ProductCircularity | type data + `BatchId` per component, recycled content per lot | released |
| ExecutedProcesses | OP10–OP90, component lots in the process BoM | released → packed |
| TechnicalData 2.0 | type values + section `AsBuilt` (date, leak rate, stroke times, cap colour) | inspected |
| QualityInspection, MeasurementValue ×2 | verdict against the recipe limits | inspected |
| CarbonFootprint | production-based PCF (A1–A3, A1, A3) | packed |
| HandoverDocumentation 2.0 | inspection certificate 3.1 (good parts) + type documents DS, OM, RI, SVHC | packed |

`contentSpecificationIds` lists the submodels present at the current stage, without MeasurementValue (two
submodels with one semanticId; the values are in QualityInspection) and without AssetLocation (logistics).
`dppStatus` is `Inactive` for rejects and lost parts, which are never placed on the market.

**Shared type data.** The static product data live once, in `aas/data/common/product_passport_pc3280.yaml`. The
type and the blueprint include named fragments of it with `$include: file#Key.Name` (a new, small extension of the
include mechanism). Lists that need per-part values (materials, recycled content, BoM) stay item lists that
include one fragment each and add the batch.

**Lots originate on the shop floor.** The assembly cell FMU gets a String output `last_lots`, reported with
`part_released` (`lots`). Each feeder of the cell changes its lot after its own number of parts (120 … 600).
The lot formats follow the supplier: in-house `L<YYWW>-<seq>`, die-caster cast date `DGP-<YYMMDD>-F/R`,
`DTS-<YYMM>-<seq>`, `NRN-<YY>-<seq>`, `KTW-<YY>-<seq>`. The change is small: one output, one UNS event field,
generated AID/AIMC/OperationalData. The MES therefore stops inventing lots. A fallback (blueprint lots shifted
every 250 parts) remains only for older simulation builds. Recycled content per lot stands for the supplier's
lot certificate. It is simulated deterministically within ±15 % of the declared type average.

**Inspection certificate.** The MES renders a one-page PDF with a minimal PDF writer of its own (`mes/pdf.py`,
standard Helvetica fonts, WinAnsi, about 7 KB, searchable, deterministic). This adds no dependency to the
services image. Pillow, used for the static documents, would rasterise the text (about 250 KB per part). The
certificate and the type documents are uploaded as File attachments. BaSyx stores identical content only once
(SHA-256 + size), so the four type documents per part cost no storage after the first part.

**DPP API service.** `dpp-api` in the compose stack, host port 8093, same database, read-only use,
`GENERAL_EXTERNALURL=http://localhost:8091` so attachment links point to the AAS environment. History endpoints
are not enabled: they need BaSyx history in the AAS environment as well, and that would snapshot every bridge
value write.

## Consequences

- `GET http://localhost:8093/v1/dpps/<urlencoded AAS id>` and `…/dppsByProductId/<urlencoded Digital Link>`
  return the item passport. The Godot inspector offers *Open passport (DPP API)* for workpieces.
- The BaSyx web UI (aas-gui) has no DPP view. It keeps showing the same AAS and submodels from port 8091.
- `GET /v1/dppsByIdAndDate` (history) returns 404 (O40).
- `representation=full` returns 422 for item passports: DPP API 1.1.0 does not convert RelationshipElement and
  ReferenceElement (BoM relations, QualityInspection references). The default compressed representation works (O38).
- A packed part costs five attachment uploads (one new object, four deduplicated) besides the submodel PUTs.
- The batch ids use a project-specific statement `BatchId` with a generated concept description. HS 1.1 has no
  batch element, and CoManagedEntities may not carry specificAssetIds (O39).
