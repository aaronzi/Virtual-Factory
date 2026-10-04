# ADR-0028: Supplier data exchange - second AAS environment, batch AAS and federated batch footprints

- Status: accepted
- Date: 2026-10-03
- Extends: [ADR-0021](0021-item-level-dpp-basyx-dpp-api.md), [ADR-0023](0023-discovery-registry-resolution-and-gs1-resolver.md),
  [ADR-0025](0025-service-decomposition-sustainability-erp.md)

## Context

The PCF of a part (aas-model.md §6a) took the component footprints (A1) from the CarbonFootprint of the component
type AAS (`CMP_*`): one declared average per type, the same for every batch. The as-built BoM recorded the batch of
every component (reported by AC01, `part_released.lots`), but batches had no data of their own, and all AAS lived
in the plant's environment. In real supply chains the supplier publishes the data of its products and delivered
batches itself (in its own or a hosted AAS environment, increasingly through a dataspace), and the customer finds
them via discovery/registry. Primary, batch-specific footprint data from suppliers is what PACT and the Catena-X
PCF exchange are about, including a data-quality statement (primary vs secondary data). ADR-0023 made all clients
resolve through a list of environments, and ADR-0025 put the interface `SupplierFootprints.footprint(bom_line,
batch)` with `ChainedFootprints` into the sustainability service for exactly this step.

## Decision

**1. A supplier AAS environment, operated separately.** A second BaSyx Go stack (`supplier-db` PostgreSQL,
`supplier-config`, `supplier-provisioner`, `aasenvironment-go:1.1.0` as `supplier-aas-env` on port **8191**,
`GENERAL_EXTERNALURL=http://localhost:8191`, registry integration on, no MQTT eventing, no DPP API). The plant's
services reach it only through discovery/registry and the supplier portal's REST API, never through its database.

- **One environment for the four suppliers** (Druckguss Pfalz, Dichtungstechnik Süd, Normteile Rhein-Neckar,
  Kunststofftechnik Westrich) - a hosted "supplier hub" as SMEs use it. Each company keeps **its own id namespace**
  (`idBase: https://virtual-factory.example/<company>/ids` in the asset data, new optional key of the template
  engine). Splitting into one environment per supplier later is a data move plus one more entry in
  `VF_AAS_REGISTRIES`; the clients do not change. Four full BaSyx stacks would quadruple containers and memory for
  no new behaviour.
- **Who hosts what.** The supplier environment holds the company AAS (IDTA CompanyData, ContactInformations), the
  **supplier's product type AAS** of the five purchased articles (Nameplate, declared CarbonFootprint, material
  composition; globalAssetId = GS1 Digital Link of the article's GTIN, specific asset ids `manufacturerPartId`,
  `gtin`) and the **batch AAS** of delivered lots. The plant keeps its `CMP_*` AAS: the **customer's purchased-part
  view** (customer part number, values as approved at the first-sample inspection, BoM link from PC3280_TYPE), the
  fallback when no batch data exist. Both carry the specific asset id `gtin`, so `lookup(gtin=...)` over the
  federation finds both views of the same trade item. Data in `aas/data/supplier/` (assets, batch blueprint,
  `batch_profiles.yaml`), built by the same provisioner (`uv run -m provisioner build|check|upload --data
  supplier`, preload `infra/basyx/preload-supplier`); the main build is unchanged.

**2. Batch lifecycle: despatch advice on line-side staging (ship-to-line).** The suppliers deliver their containers
directly to the feeders of AC01. When the MES sees a lot for the first time (first released part built from it), it
reports the staging to the ERP (`POST /api/material-staging`, background thread, repeated with the next part after a
failure). The ERP asks the **supplier portal** (`services/supplier`, port **8190**) for the despatch advice of that
lot (`POST /api/despatch-advices`), posts the goods receipt with the supplier's quantity (`Source =
despatch-advice`) and stores the reference to the supplier batch in its batch master (`SupplierBatch`: Digital
Link, AAS id, shell link, material certificate, batch PCF, despatch advice number). The portal publishes the batch
AAS when it issues the despatch advice - idempotent, once per lot. In-house lots (`L<YYWW>-n`) get no despatch
advice; their batches still appear with the backflush (ADR-0025).

- Batch AAS (blueprint `aas/data/supplier/blueprints/batch_instance.yaml`, tag `BATCH_<lot>`, derivedFrom the type,
  globalAssetId `https://virtual-factory.example/01/<GTIN>/10/<lot>`, specific asset ids `manufacturerPartId`,
  `batchId`, `customerPartId`): **BatchInformation** (custom template in the YAML DSL - no IDTA template covers
  batches; the VF vocabulary is prescribed to the suppliers in the data exchange agreement: batch id, article
  numbers, quantity, production and despatch date, site, despatch advice, certificate id, mean mass, recycled
  content), **CarbonFootprint** (IDTA 1.0, per piece, PACT-like: PcfCO2eq of this batch, `PrimaryDataShare`,
  `BatchId`), **ProductMaterialComposition** (type composition scaled to the measured mass, `BatchId` per
  material) and **HandoverDocumentation** with the **inspection certificate 3.1 (EN 10204)** as generated PDF
  (chemical analysis / material properties / dimensions against limits; PDF writer moved to `vf_common.pdf`).
- Batch values are simulated deterministically from the lot number (`batch_profiles.yaml`): batch PCF = declared
  × (1 ± spread) − credit × (recycled share − declared share); recycled shares come from
  `vf_common.lot_values.recycled_share`, which the MES uses for the passport's circularity too, so passport and
  supplier batch state the same values.
- Rejected: **pre-provisioning** a window of the deterministic lot sequence - the AC01 serial counter is retentive,
  so the lot index is unbounded, and a supplier does not publish batches before it produced them (hundreds of AAS
  in the preload). **Portal shipping ahead of demand** (call-offs) - only the shop floor knows which lot index a
  feeder stages next. **Batch AAS created by the sustainability service on a miss** - the customer would write
  the supplier's data. The chosen trigger runs within a second of the first release from a lot, long before its
  first part is packed (≥ 20 s); every step is retried, and a missing batch falls back to the type average.
- Simulation shortcut (documented): the portal materialises a lot - record, AAS, certificate - when the customer
  first asks for its despatch advice, instead of at a real despatch event.

**3. Federation.** The sustainability service gets `VF_AAS_REGISTRIES=vf=http://aas-env:8091,supplier=http://
supplier-aas-env:8191` and `VF_AAS_ENDPOINT_MAP` for both public URLs (container ↔ host); Godot's `aas_registries`
lists both environments at their host URLs. Services that never need supplier data (bridge, MES, ops gateway,
edge, resolver) keep their single environment, so a supplier outage cannot affect them. `AasResolver` now skips an
unreachable environment and raises its error only if no other environment knows the id (callers retry instead of
concluding "unknown"); partial lookups/scans return what the reachable environments know.

**4. As-built BoM: purchased batches are SelfManagedEntities.** Now that a purchased batch has its own AAS, its BoM
node is a `SelfManagedEntity` with globalAssetId = the batch's Digital Link (HS 1.1: assets with their own AAS);
in-house lots stay `CoManagedEntity` without asset ids (AASd-014). The MES composes the Digital Link from the
GTIN of the supplier article and the lot - as a scanner does from the GS1-128 label of the container - so the BoM
does not depend on the supplier environment being reachable when the part is released; the node keeps `BatchId`
and the `SameAs` to the type BoM node. This revises the rule of §6b ("batches have no AAS").

**5. Sustainability: supplier source with data quality.** `SupplierBatchFootprints` sits in front of
`ComponentTypeFootprints`: component type asset id → registry descriptor → specific asset id `gtin` (purchased
parts only) → batch Digital Link → federated discovery → batch AAS → CarbonFootprint (first entry: PcfCO2eq,
PrimaryDataShare). Found footprints are cached per batch (immutable after publication); unknown batches are asked
again after 30 s, unreachable environments are not cached. Every component footprint carries `dataQuality`
(`primary` = supplier batch data, `secondary` = declared type average) and the supplier's primary data share.
CarbonFootprint 1.0 has no data-quality elements (only `ExternalPcfApi` to point at a PCF exchange endpoint), so
the part's CarbonFootprint gets extra properties: `PrimaryDataShare` (PACT primaryDataShare, emissions-weighted:
supplier primary shares for A1, A3 = measured energy and losses of LINE01 counts as primary) on the total and A1
entries, and `SupplierSpecificDataShare` (share of A1 taken from supplier batch footprints) on the A1 entry.

**6. Godot.** The inspector shows *Open asset AAS* when the selected tree element is an Entity with a
globalAssetId (BoM batch nodes, type BoM nodes) and opens it via discovery over `aas_registries` - for a supplier
batch, the AAS in the supplier environment. *Open type AAS* of a batch opens the supplier's product type.

**7. Dataspace (EDC / Catena-X) - documented, not implemented.** Here the plant reads the supplier registry and
repository directly (open HTTP, no contract). In Catena-X the supplier would expose its batch AAS behind its
**Eclipse Dataspace Connector**: the shell descriptors in the supplier's (or a central) Digital Twin Registry
carry a `subprotocolBody` with the asset id and the supplier's connector (DSP) endpoint, and the BPN-based
**EDC Discovery** maps the supplier's BPN to that endpoint. The sustainability service would then: discover the
connector (BPN discovery / EDC discovery), negotiate a contract for the batch's PCF asset (usage policy, e.g.
"PCF exchange"), obtain an EDR token from the consumer connector and call the submodel through the provider's
data plane - or use the Catena-X PCF exchange API (PACT, `ExternalPcfApi` in CarbonFootprint) instead of reading
the submodel. In code this replaces `RegistryConfig`/`InfrastructureClient` with an EDC-aware variant and the
repository client with a data-plane client carrying the EDR token; the `SupplierFootprints` interface and the
fallback stay. Open issue O59.

## Alternatives

- **One environment per supplier**: most realistic for large suppliers, no new behaviour for the plant (the
  registry list grows), four times the containers - see 1.
- **Supplier data copied into the plant environment** (supplier uploads into our repository): no federation, and
  the customer would host the supplier's data.
- **Batch PCF in the ERP batch record only** (despatch advice as data carrier): realistic for EDI, but bypasses
  the AAS; kept as additional reference (`SupplierBatch.PcfCO2eqPerPiece`), the PCF is read from the batch AAS.
- **Batch nodes CoManaged with a ReferenceElement to the batch AAS**: keeps AASd-014 trivially, but a reference to
  a foreign environment's AAS id is less robust than an asset id resolved by discovery, and contradicts HS 1.1.

## Consequences

- \+ Part PCFs use supplier primary data for the five purchased components (about 30 % of A1 by mass of CO₂e) and say
  so (data-quality properties, KPIs `avgPrimaryDataShare`, `avgSupplierSpecificShareA1`); batches without supplier
  data degrade gracefully to the declared average.
- \+ The federation of ADR-0023 is exercised end to end: services and the Godot inspector resolve AAS of a second
  environment by asset id; the as-built BoM links each part to the supplier's batch.
- \+ The ERP batch master links goods receipts to despatch advices, certificates and batch AAS.
- − Five more containers (supplier-db, -config, -provisioner, -aas-env, supplier portal); the supplier DB is on
  tmpfs like the plant's, so batch AAS disappear with `down` (they are re-created on the next staging report,
  with identical values).
- − The batch lifecycle is a simulation shortcut (O60); data quality covers only the primary data share (O61).
