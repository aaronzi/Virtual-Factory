# Upstream findings: BaSyx Go, basyx-python-sdk, AAS specifications, IDTA submodel templates

> Status: 2026-10-04. Collected from building the Virtual Factory (M0–M9b): open issues, ADRs, workaround code and
> session notes, each **re-verified** against the pinned versions. **Nothing has been filed upstream yet**; the
> last section lists draft issue titles for review.

## Pinned versions and evidence

| Component | Version | How verified |
|---|---|---|
| BaSyx Go AAS Environment, DPP API | `eclipsebasyx/aasenvironment-go:1.1.0`, `dppapi-go:1.1.0` (source tag `v1.1.0`, 2026-09-28) | live requests against the running open-profile stack (8091, 8093) with temporary resources `urn:upstream-test:*` (deleted afterwards); code locations at tag `v1.1.0` |
| BaSyx Go ABAC | same | **verified in the secure profile on 2026-10-03, not re-run** (ADR-0027, O58, `tools/tests/test_secure_stack.py`); code locations at `v1.1.0` |
| basyx-python-sdk | 2.2.0 (`uv.lock`) | minimal Python reproductions |
| IDTA submodel templates | 30 templates as served by the IDTA SMT repository `https://smt-repo.admin-shell-io.com/api/v3.0` (fetched 2026-10-03, vendored in `aas/templates/idta`, CDs in `concept_descriptions.json`, full CD dump of 2 846 CDs) | scripted scans of the vendored JSON |
| AAS specifications | Part 1 metamodel V3.0.6 / V3.2.0, Part 2 API V3.0.4 / V3.2.0, Part 3a IEC 61360 V3.1, Part 4 Security V3.1, IDTA 02008-1-1 (TimeSeries) | spec sources on GitHub (`admin-shell-io/aas-specs-*`) |

Template findings refer to the JSON served by the SMT repository. The files on GitHub
(`admin-shell-io/submodel-templates/published/...`) may differ in details; where an open GitHub issue reports the
same defect it is linked.

**Classification:** *Bug* (implementation contradicts its spec or its own documentation) · *Spec gap* (spec missing
or ambiguous) · *Template defect* (error in a published template/CD) · *Template gap* (missing modelling
capability) · *Usability* (works as specified/documented, but costs users effort or causes errors).
**Severity** (impact on users): *High* - wrong results or blocked use case without an obvious workaround;
*Medium* - interoperability break or a workaround in code needed; *Low* - cosmetic, documentation, edge case.
**Upstream status** searched on 2026-10-04 in `eclipse-basyx/basyx-go-components`, `eclipse-basyx/basyx-python-sdk`,
`admin-shell-io/submodel-templates`, `admin-shell-io/aas-specs-metamodel`, `aas-specs-api`, `aas-specs-security`,
`aas-specs-iec61360`, `aas-test-engines` (full issue lists, open and closed).

## Summary

| ID | Title | Class | Severity | Upstream |
|---|---|---|---|---|
| [BSG-01](#bsg-01) | Value-only `$value` uses JSON strings for numbers and booleans, rejects typed JSON | Bug | Medium | not found |
| [BSG-02](#bsg-02) | `semanticId` query only accepts base64url Reference JSON and matches the reference type exactly | Usability | Medium | spec: aas-specs-api#342 |
| [BSG-03](#bsg-03) | No metamodel constraint validation on write (AASd-021/108/109/120 violations are stored) | Usability | Medium | spec: aas-specs-api#112 |
| [BSG-04](#bsg-04) | Delegation allowlist needs the resolved IP of every target, no CIDR | Usability | Low | related #520 (closed) |
| [BSG-05](#bsg-05) | Change events only at submodel granularity, no element path or value | Usability | Low | related #188 (open) |
| [BSG-06](#bsg-06) | Shell descriptors embed submodel descriptors without idShort and semanticId | Usability | Low | not found |
| [BSG-07](#bsg-07) | `/query/submodel-descriptors` applies `limit` before the query: empty pages with cursor | Bug | Low | related #166 (closed) |
| [BSG-08](#bsg-08) | Deleting an AAS leaves an empty discovery entry (200 `[]` instead of 404) | Bug | Low | not found |
| [BSG-09](#bsg-09) | DPP API: `dppsByProductId` matches `globalAssetId`, not `uniqueProductIdentifier` | Bug | High | related #528 (closed) |
| [BSG-10](#bsg-10) | DPP API: DPP id must equal the AAS id, otherwise the passport is unreachable by id | Usability | Medium | documented (CHANGELOG, #691) |
| [BSG-11](#bsg-11) | DPP API: `representation=full` returns 422 for RelationshipElement, ReferenceElement, Range, Blob, ... | Bug | Medium | not found |
| [BSG-12](#bsg-12) | DPP API: only one submodel per semanticId, others are dropped silently | Usability | Medium | not found |
| [BSG-13](#bsg-13) | ABAC: denied value-only PATCH answers HTTP 500 instead of 403 | Bug | Medium | not found |
| [BSG-14](#bsg-14) | ABAC: `$sm` formulas break the DPP API's AAS read ("cannot extract alias") | Bug | Medium | not found |
| [BSG-15](#bsg-15) | ABAC: rules for `ANONYMOUS` also apply to authenticated callers | Spec gap | Low | design: #574; spec: see AAS-03 |
| [BSG-16](#bsg-16) | MQTT change events bypass ABAC | Usability | Low | documented |
| [BSP-01](#bsp-01) | Entities serialised with `"specificAssetIds": []` (JSON schema minItems 1) | Bug | Medium | **#636 (open)** |
| [BSP-02](#bsp-02) | `KeyTypes` lacks `Identifiable` and `Referable`: valid JSON fails with `KeyError` | Bug | Medium | not found (misattributed in SMT #245) |
| [BSP-03](#bsp-03) | `AASXWriter.write_aas()` omits CDs referenced by ExternalReference semanticIds | Usability | Medium | #234 (closed, by design) |
| [AAS-01](#aas-01) | Part 2: encoding and matching of the `semanticId` query parameter undefined | Spec gap | Medium | **aas-specs-api#342 (open)** |
| [AAS-02](#aas-02) | Part 2: servers need not validate metamodel constraints on write | Spec gap | Medium | aas-specs-api#112 (open, partial) |
| [AAS-03](#aas-03) | Part 4: `ANONYMOUS` undefined for requests that carry a token | Spec gap | Low | not found |
| [AAS-04](#aas-04) | No way to identify a batch without an AAS of its own (AASd-014) | Spec gap | Low | metamodel#483 (closed) |
| [AAS-05](#aas-05) | No standard change-event interface | Spec gap | Low | aas-specs-api#41, #297, #557, #600 (open) |
| [AAS-06](#aas-06) | No standard way to bind an Operation to its implementation | Spec gap | Low | not found |
| [SMT-X-01](#smt-x-01) | Cardinality qualifier: 4 type spellings, 5 non-standard values | Template defect | Medium | #159, #279 (open) |
| [SMT-X-02](#smt-x-02) | Submodel semanticId as (mostly dangling) ModelReference in 21 of 30 templates | Template defect | Medium | #224, #209 (open) |
| [SMT-X-03](#smt-x-03) | Whitespace inside identifiers (semanticIds, CD ids, units) in 9 templates | Template defect | Medium | #210 (open); #128, #129 closed but still present |
| [SMT-X-04](#smt-x-04) | 54 SubmodelElementList children carry an idShort (AASd-120) in 8 templates | Template defect | Low | #245 (open, MI only) |
| [SMT-X-05](#smt-x-05) | Semantic ids without concept description in the SMT repository | Template defect | Medium | #142 (open, HS only) |
| [SMT-X-06](#smt-x-06) | CD quality: 4 IEC 61360 template ids, self-referencing data specifications, no dataType, units misused | Template defect | Low | not found |
| [SMT-X-07](#smt-x-07) | One-character idShorts invalid from metamodel V3.1 (AssetLocation, Models3D) | Template defect | Low | #272, #273 (open) |
| [SMT-AID-01](#smt-aid-01) | AID 1.1: 24 `enum` lists without `valueTypeListElement` (AASd-109) | Template defect | Medium | **#323 (open)** |
| [SMT-AID-02](#smt-aid-02) | AID 1.1: no template structure for actions and events | Template gap | Medium | not found |
| [SMT-AID-03](#smt-aid-03) | AID 1.1: one `forms` per affordance; no acknowledgement/response topic | Template gap | Medium | not found |
| [SMT-AID-04](#smt-aid-04) | AID 1.1: boolean binding terms typed `xs:string` | Template defect | Low | not found |
| [SMT-AL-01](#smt-al-01) | AssetLocation 1.0: leading spaces in IRDIs, 41 semantic ids without CD, no units for coordinates | Template defect | Medium | #224 (open, partial) |
| [SMT-AL-02](#smt-al-02) | AssetLocation 1.0: idShort typo `AreaDesciption` | Template defect | Low | not found |
| [SMT-CAP-01](#smt-cap-01) | CapabilityDescription 1.0: duplicate `SMT/Cardinality` qualifier (AASd-021) | Template defect | Medium | not found |
| [SMT-CAP-02](#smt-cap-02) | CapabilityDescription 1.0: inconsistent PropertyRange semanticIds, string Range | Template defect | Low | not found |
| [SMT-CC-01](#smt-cc-01) | Control Component 2.0: no skill → endpoint relation | Template gap | Medium | **#214 (open)** |
| [SMT-CC-02](#smt-cc-02) | Control Component Type 2.0: qualifier `SMT/SMT/Cardinality`; CDs missing | Template defect | Low | not found |
| [SMT-PCF-01](#smt-pcf-01) | CarbonFootprint 1.0: no data-quality, primary-data or assurance elements | Template gap | Medium | not found |
| [SMT-HS-01](#smt-hs-01) | HierarchicalStructures 1.1: Node description and CD copied from EntryNode | Template defect | Low | related #142 (open) |
| [SMT-HS-02](#smt-hs-02) | HierarchicalStructures 1.1: no batch/lot concept for as-built BoMs | Template gap | Low | not found |
| [SMT-MI-01](#smt-mi-01) | MaintenanceInstructions 1.0: semanticId is a ModelReference with key type `Identifiable` | Template defect | Medium | #245 (open) |
| [SMT-MI-02](#smt-mi-02) | MaintenanceInstructions 1.0: `htthttps://`, misspelled/duplicated semanticIds and idShorts | Template defect | Low | #245, #279 (open, partial) |
| [SMT-PP-01](#smt-pp-01) | ProcessParameters 1.0: id and semanticId use `https://admin-shell-io/...` | Template defect | Medium | not found |
| [SMT-EP-01](#smt-ep-01) | ExecutedProcesses 1.0: start/end times typed `xs:string` | Template defect | Low | not found |
| [SMT-TS-01](#smt-ts-01) | TimeSeries 1.1: no CDs for UtcTime/TaiTime/RelativeTimeDuration | Template defect | Medium | not found |
| [SMT-TS-02](#smt-ts-02) | TimeSeries 1.1: segment times typed `xs:string` (spec: TIMESTAMP), CD text copied | Template defect | Low | not found |
| [SMT-PDT-01](#smt-pdt-01) | PowerDriveTrainSizing 1.0: idShort typos, leading-space IRDIs, ModelReference semanticIds | Template defect | Low | related #248 (open) |
| [SMT-CD-01](#smt-cd-01) | CompanyData 1.0: IEC 61360 `unit` used for data types in 67 CDs | Template defect | Low | not found |
| [SMT-CI-01](#smt-ci-01) | ContactInformations 1.0 / SoftwareNameplate 1.0: broken TypeOfCommunication and IPCommunication ids | Template defect | Low | #206, #210 (open) |
| [OT-01](#ot-01) | aas-test-engines 1.0.3 checks only ContactInformations 1.0 and Nameplate 2.0 | Usability | Low | related #96 (closed) |

Counts: BaSyx Go 16 (Bug 7, Usability 8, Spec gap 1), basyx-python-sdk 3 (Bug 2, Usability 1), AAS
specifications 6 (Spec gap 6), submodel templates 29 (Template defect 24, Template gap 5), other tooling 1.

---

## 1. Eclipse BaSyx Go 1.1.0

### 1.1 AAS Environment / Submodel Repository API

<a id="bsg-01"></a>

#### BSG-01 Value-only `$value` uses JSON strings for numbers and booleans, rejects typed JSON

- **Component:** AAS Environment 1.1.0, `PATCH/GET .../submodel-elements/{path}/$value`, `GET /submodels/{id}/$value`
- **Class / severity:** Bug / Medium - every client that follows the spec fails on writes and must special-case reads.
- **Reproduction** (Property `D` `xs:double`, `B` `xs:boolean`, `I` `xs:int`):

  ```bash
  curl -X PATCH -H 'Content-Type: application/json' -d '0.25'   "$AAS/submodels/$SM/submodel-elements/D/\$value"  # 400
  curl -X PATCH -H 'Content-Type: application/json' -d '"0.25"' "$AAS/submodels/$SM/submodel-elements/D/\$value"  # 204
  curl "$AAS/submodels/$SM/\$value"   # {"B":"false","D":"0.25","I":"7",...}
  ```

  400 text: `failed to unmarshal SubmodelElementValue: json: cannot unmarshal number into Go value of type
  []jsontext.Value` (same for `false`, `7`).
- **Expected:** ValueOnly encoding (Part 1 V3.1/V3.2 *Mappings › ValueOnly*, data type table; Part 2 V3.0 for
  V3.0): `xs:boolean` → JSON boolean, `xs:int`/`xs:double`/... → JSON number, dates/strings → JSON string. Reads
  should return `{"B": false, "D": 0.25, "I": 7}`, writes should accept them.
- **Actual:** only the JSON-string form is accepted and returned. Cause:
  `internal/common/model/model_submodel_element_value_deserializer.go:20-39` tries map → string → "ambiguous" →
  list and never a JSON number/boolean.
- **Workaround:** `BasyxClient.set_value` sends the lexical value as a JSON string
  (`services/vf_common/src/vf_common/basyx.py:95-101`); readers convert by `valueType`.

<a id="bsg-02"></a>

#### BSG-02 `semanticId` query only accepts base64url Reference JSON and matches the reference type exactly

- **Component:** AAS Environment 1.1.0, `GET /submodels?semanticId=` (also `/shells` and registries)
- **Class / severity:** Usability / Medium - clients written against the literal Part 2 text get 400; references
  of the "wrong" type are never found.
- **Reproduction** (submodel with ExternalReference/GlobalReference `urn:upstream-test:sem:1`):

  | `semanticId=` value | Result |
  |---|---|
  | base64url(`urn:upstream-test:sem:1`) | 400 `COMMON-APIOBJECT-JSON invalid character 'u'` |
  | `urn:upstream-test:sem:1` (unencoded) | 400 `COMMON-APIPARAM-ALPHABET expected base64url` |
  | base64url(`{"type":"ExternalReference","keys":[{"type":"GlobalReference","value":"urn:..."}]}`) (compact, pretty, keys first) | 200, found |
  | base64url(`{"type":"ModelReference","keys":[{"type":"Submodel","value":"urn:..."}]}`) | 200, **not found** |

- **Expected:** Part 2 V3.0.4 and V3.2.0 (`Part2-API-Schemas`, parameter `SemanticId`) describe the parameter as
  "the value of the semantic id reference (BASE64-URL-encoded)" - the most natural reading is the key value. The
  spec does not define reference encoding or matching (AAS-01). BaSyx's choice (full Reference JSON, exact match)
  is defensible since metamodel issue #350 removed the equivalence of `ModelReference[Submodel]` and
  `GlobalReference`, but it is undocumented in the error and silently misses the 21 IDTA templates whose
  semanticId is a ModelReference (SMT-X-02).
- **Code:** `internal/submodelrepository/api/api_submodel_repository_api_service.go:675-681` →
  `internal/common/api_parameters.go:139-150` (decodes a JSON object only).
- **Workaround:** `BasyxClient.list_submodels` builds the Reference JSON (`basyx.py:66-73`); AID/AIMC/DppMetadata
  lookups query both reference forms (`services/vf_common/src/vf_common/aid.py:161-166`, `mes/store.py:26`).

<a id="bsg-03"></a>

#### BSG-03 No metamodel constraint validation on write

- **Component:** AAS Environment 1.1.0, `POST/PUT /submodels`
- **Class / severity:** Usability / Medium - invalid models are stored and served; strict clients
  (basyx-python-sdk, aas-core) then fail on read, far away from the cause.
- **Reproduction:** each `POST /submodels` below returned **201** and the element was stored unchanged:

  | Element | Violates |
  |---|---|
  | SML `typeValueListElement: Property` without `valueTypeListElement` | AASd-109 |
  | Property with two qualifiers of type `T` | AASd-021 |
  | SML child with `idShort` | AASd-120 |
  | SML `typeValueListElement: Property` containing a MultiLanguageProperty | AASd-108 |
  | idShort `X` | AASd-002 (V3.1+ form) |
  | semanticId key value `" 0173-1#02-ABH961#002"` (leading space) | none, but never matches its CD |

- **Expected:** Part 2 asks for validation only for bulk requests ("should", `http-rest-api.adoc` §Bulk) - see
  AAS-02. Rejecting (400) or at least warning on constraint violations would match what BaSyx already does for
  some V3.1 idShort rules during AASX import (warnings, R2).
- **Workaround:** the provisioner validates every package strictly (basyx-python-sdk + aas-test-engines,
  `uv run tools/check_aasx.py`) before upload (ADR-0011).

<a id="bsg-04"></a>

#### BSG-04 Delegation allowlist needs the resolved IP of every target, no CIDR

- **Component:** Submodel Repository / AAS Environment 1.1.0, `SMREPO_DELEGATION_TRUSTED_HOSTS`
- **Class / severity:** Usability / Low - deliberate DNS-rebinding protection, but in Docker/Kubernetes target
  IPs are dynamic, so deployments need static IPs.
- **Reproduction:** `SMREPO_DELEGATION_TRUSTED_HOSTS=ops-gateway:8095` (and `ops-gateway:8095,172.16.0.0/12`),
  invoke an Operation with `invocationDelegation=http://ops-gateway:8095/...` → 502 `SMREPO-RSLVDELAUTH-
  UNTRUSTEDRESOLVED delegation URL address "ops-gateway:8095" resolved to addresses that are not in
  SMREPO_DELEGATION_TRUSTED_HOSTS allowlist` (2026-10-03).
- **Expected:** an option to trust the resolved addresses of an allowlisted name, or CIDR entries.
- **Actual:** `internal/submodelrepository/api/operation_delegation_security.go:199-225` (exact authority or
  `host:*` only), `:259-287` (every resolved IP must be listed). The example
  `examples/BaSyxDelegatedOperationsExample` documents the static-IP pattern; #520 (closed) hit the same.
- **Workaround:** fixed compose subnet and IP for the ops gateway (`infra/docker-compose.yml:42, 121`, O20).

<a id="bsg-05"></a>

#### BSG-05 Change events only at submodel granularity

- **Component:** AAS Environment 1.1.0, MQTT eventing (experimental)
- **Class / severity:** Usability / Low - documented (`docu/eventing/mqtt_eventing.md`: nested elements and
  values "use the existing mutation triggers"); consumers must re-read the whole submodel per event.
- **Reproduction:** value PATCH of one Property → one message on `vf/basyx/submodelrepository/submodel/updated`
  with `data: {"globalAssetIds":[...],"semanticId":{...},"submodelId":"urn:upstream-test:sm:1"}` - no element
  path, no value, no operation.
- **Expected (feature):** element-level events (idShortPath, change kind, optionally the value-only value), so
  consumers need not re-read.
- **Workaround:** consumers re-read the submodel and reload every 5 min (R1, ADR-0015).

### 1.2 Registry and discovery integration

<a id="bsg-06"></a>

#### BSG-06 Shell descriptors embed submodel descriptors without idShort and semanticId

- **Component:** AAS Environment 1.1.0 registry integration
- **Class / severity:** Usability / Low - both attributes are optional in Part 2, but the same server fills them in
  `/submodel-descriptors`; clients resolving "the AAS's Nameplate" need one extra call per submodel.
- **Reproduction:** `POST /submodels` (idShort and semanticId set), then `POST /shells` referencing it →
  `GET /shell-descriptors/{aas}`: `submodelDescriptors: [{"id": "...", "endpoints": [...]}]`;
  `GET /submodel-descriptors/{sm}` returns idShort and semanticId.
- **Code:** `internal/registrysync/config.go:170-189` (`buildEmbeddedSubmodelDescriptors`: id and endpoints only),
  while `internal/aasenvironment/custom_aas_repository_service.go:840-866` builds full descriptors for later
  submodel-ref additions.
- **Workaround:** `AasResolver` reads idShort/semanticId from the submodel registry
  (`services/vf_common/src/vf_common/resolver.py:141-160`, `registry.py:113-123`).

<a id="bsg-07"></a>

#### BSG-07 `/query/submodel-descriptors` applies `limit` before the query

- **Component:** AAS Environment 1.1.0, `POST /query/submodel-descriptors` (AAS query language)
- **Class / severity:** Bug / Low - results are complete when all pages are read, but pages are mostly empty, so
  the query saves no round trips over listing all descriptors.
- **Reproduction:** 211 descriptors, 10 match `{"$condition":{"$eq":[{"$field":"$smdesc#semanticId.keys[0].value"},
  {"$strVal":"https://admin-shell.io/idta/AssetInterfacesMappingConfiguration/2/0/Submodel"}]}}`. Results per page:
  default limit `[5, 5, 0]`; `limit=5` → 43 pages `[1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, ...]`; `limit=20` →
  `[1, 0, 1, 1, 2, 1, 0, 1, 2, 1, 0]`, each with a cursor.
- **Expected:** `limit` caps the number of *matching* results (Part 2 paging: "maximum number of elements in the
  response array"); a page without results should end the paging.
- **Code:** `internal/smregistry/api/api_submodel_registry_api_service.go:114-160` passes the query as an
  authorization-style filter into the normal list statement; related ticket #166 ("Apply Column Fragment
  Filtering After LIMIT", closed).
- **Workaround:** none needed; we scan `/submodel-descriptors` (O45).

<a id="bsg-08"></a>

#### BSG-08 Deleting an AAS leaves an empty discovery entry

- **Component:** AAS Environment 1.1.0 discovery integration
- **Class / severity:** Bug / Low - stale entries accumulate (our MES deletes hundreds of workpiece AAS per hour).
- **Reproduction:** `POST /shells` (globalAssetId set), `DELETE /shells/{id}` → `GET /lookup/shells/{id}` answers
  `200 []`; an id that never existed answers 404 `DISC-404-GetAllAssetLinksById-NotFound`. `DELETE
  /lookup/shells/{id}` removes the entry.
- **Expected:** the discovery entry is removed with the AAS (404 afterwards), as for the registry descriptors.
- **Code:** not located.
- **Workaround:** none (cosmetic for us).

### 1.3 DPP API 1.1.0

<a id="bsg-09"></a>

#### BSG-09 `dppsByProductId` matches `globalAssetId`, not `uniqueProductIdentifier`

- **Component:** DPP API 1.1.0, `GET /v1/dppsByProductId/{productId}` (and `POST /v1/dppsByProductIds`)
- **Class / severity:** Bug / High - passports whose product identifier differs from the AAS globalAssetId
  (e.g. GS1 Digital Link vs. internal asset IRI) cannot be found by product id.
- **Reproduction:** AAS `urn:upstream-test:aas:dpp-a` with globalAssetId `urn:upstream-test:asset:dpp-a` and a
  DppMetadata `uniqueProductIdentifier = urn:upstream-test:product:a`:
  - `GET /v1/dppsByProductId/urn%3Aupstream-test%3Aproduct%3Aa` → **404** `DPP-READBYPRODUCT-NOTFOUND`
  - `GET /v1/dppsByProductId/urn%3Aupstream-test%3Aasset%3Adpp-a` → 200, the passport shows
    `"uniqueProductIdentifier": "urn:upstream-test:product:a"`
- **Expected:** lookup by the passport's `uniqueProductIdentifier` (DIN EN 18222 / IDTA DPP4.0 semantics). The
  BaSyx CHANGELOG for #691 says "product-based retrieval remains available through uniqueProductIdentifier"; #528
  (closed) expected the same.
- **Code:** `pkg/dppapiservice/go/dpp_repository_service.go:825-835` passes the product id as `globalAssetIDs` to
  `internal/aasrepository/persistence/aas_database.go:1155` →
  `aas_database_query_utils.go:328-335` (`asset_information.global_asset_id`).
- **Workaround:** globalAssetId = uniqueProductIdentifier = GS1 Digital Link for all products (ADR-0021, O38).

<a id="bsg-10"></a>

#### BSG-10 DPP id must equal the AAS id

- **Component:** DPP API 1.1.0, `GET /v1/dpps/{dppId}`, `/v1/dppsByIdAndDate`
- **Class / severity:** Usability / Medium - documented ("Require ID-based DPP lookup to match both the owning AAS
  identifier and its DppMetadata.digitalProductPassportId", CHANGELOG/#691), but it forbids a separate DPP id
  scheme and makes the product lookup return ids that cannot be dereferenced.
- **Reproduction:** AAS `urn:upstream-test:aas:dpp-b` with `digitalProductPassportId = urn:upstream-test:dpp:b`:
  `GET /v1/dpps/urn%3Aupstream-test%3Adpp%3Ab` → 404, `GET /v1/dpps/urn%3Aupstream-test%3Aaas%3Adpp-b` → 404,
  but `GET /v1/dppsByProductId/<globalAssetId>` → 200 with `"digitalProductPassportId": "urn:upstream-test:dpp:b"`.
- **Expected:** resolve the DPP id through the DppMetadata (the DPP data model allows DPP id ≠ AAS id), or reject
  such passports consistently on write.
- **Code:** `pkg/dppapiservice/go/dpp_repository_service.go:1274-1309` (`resolveSubmodels(dppID, dppID)`).
- **Workaround:** DPP id = AAS id (ADR-0021).

<a id="bsg-11"></a>

#### BSG-11 `representation=full` returns 422 for most element types

- **Component:** DPP API 1.1.0, `?representation=full`
- **Class / severity:** Bug / Medium - the full representation fails for any passport with a BoM
  (RelationshipElement) or references.
- **Reproduction:** content submodel with a ReferenceElement and a RelationshipElement →
  `GET /v1/dpps/urn%3Aupstream-test%3Aaas%3Adpp-a?representation=full` → **422** `DPP-ELEM-FULL-UNSUPPORTED
  unsupported AAS element type ...`; the compressed representation (default) returns both elements.
- **Expected:** every SubmodelElement type of the content submodels is serialised (or skipped with a notice);
  the compressed representation already handles them.
- **Code:** `pkg/dppapiservice/go/dpp_serializer.go:153-174` handles only Property, SubmodelElementList,
  MultiLanguageProperty, SubmodelElementCollection, Entity and File.
- **Workaround:** clients use the compressed representation for item passports (O38, services.md *dpp-api*).

<a id="bsg-12"></a>

#### BSG-12 Only one submodel per semanticId, others are dropped silently

- **Component:** DPP API 1.1.0, content selection
- **Class / severity:** Usability / Medium - silent data loss; two MeasurementValue submodels of a part cannot
  both appear.
- **Reproduction:** two submodels with semanticId `urn:upstream-test:sem:1` (`P=1`, `P=2`) on one passport AAS →
  the passport contains only `"urn:upstream-test:sem:1": {"P": "2", ...}`.
- **Expected:** all matching submodels (e.g. as a list under the specification id), or a 409/warning.
- **Code:** `pkg/dppapiservice/go/dpp_repository_service.go:1357-1395` (`selectedBySemanticID`, newest wins).
- **Workaround:** MeasurementValue left out of `contentSpecificationIds`; the values are in QualityInspection
  (ADR-0021).

### 1.4 Access control (ABAC) - verified in secure profile on 2026-10-03, not re-run

<a id="bsg-13"></a>

#### BSG-13 Denied value-only PATCH answers HTTP 500 instead of 403

- **Component:** AAS Environment 1.1.0 with `ABAC_ENABLED`, `PATCH .../$value`
- **Class / severity:** Bug / Medium - clients treat it as a server fault and retry; monitoring raises alarms.
- **Reproduction:** service account `vf-mes` (no write right on OperationalData) → `PATCH
  /submodels/<OperationalData>/submodel-elements/<path>/$value` → 500 with text "403 Denied … ABACDENIED"
  (value not written). `tools/tests/test_secure_stack.py:95` asserts `>= 400`.
- **Expected:** 403 like PUT/POST/DELETE.
- **Code:** `internal/submodelrepository/api/api_submodel_repository_api_service.go:2388-2396` maps only
  BadRequest and NotFound; the `ErrDenied` (`common.NewErrDenied("...-ABACDENIED ...")`) raised by the persistence
  layer falls through to 500, while other handlers map it to 403.
- **Workaround:** none needed (writes are designed to be permitted); O58.

<a id="bsg-14"></a>

#### BSG-14 `$sm` formulas break the DPP API's AAS read

- **Component:** DPP API + AAS Environment 1.1.0 with ABAC
- **Class / severity:** Bug / Medium - semantic-id or idShort based passport section rules are impossible.
- **Reproduction:** DPP API rule with a formula on `$sm#idShort` → `GET /v1/dpps/{id}` → 404 "cannot extract
  alias from column submodel.id_short".
- **Code:** `internal/common/model/grammar/logical_expression_to_sql.go:1900-1906`.
- **Workaround:** fragment filter on `$aas#submodels[]` with a regex on the submodel id (depends on our id
  scheme): `tools/security_abac.py:50-60` (ADR-0027, O58).

<a id="bsg-15"></a>

#### BSG-15 Rules for `ANONYMOUS` also apply to authenticated callers

- **Component:** AAS Environment / DPP API 1.1.0 ABAC
- **Class / severity:** Spec gap / Low - intended in BaSyx (#574: "ANONYMOUS may be used alone or together with
  claims"), but the Part 4 definition says ANONYMOUS means "the request does not contain an access token", so a
  rule cannot target token-less requests only (e.g. a reduced public passport) - see AAS-03.
- **Code:** `internal/common/security/abac_engine_attributes.go:35-67` (`hasAnonymousSubject` satisfies the
  attribute gate regardless of claims).
- **Workaround:** public sections are a subset of every role's sections (ADR-0027).

<a id="bsg-16"></a>

#### BSG-16 MQTT change events bypass ABAC

- **Component:** AAS Environment 1.1.0 eventing
- **Class / severity:** Usability / Low - documented ("HTTP access rules do not filter MQTT subscribers",
  `docu/eventing/mqtt_eventing.md`); events reveal ids, semanticIds and globalAssetIds of submodels a subscriber
  may not read.
- **Expected (feature):** audience-specific topics or payload filtering derived from the READ rules.
- **Workaround:** broker ACL restricts `vf/basyx/#` to service accounts (O56).

---

## 2. basyx-python-sdk 2.2.0

<a id="bsp-01"></a>

### BSP-01 Entities serialised with `"specificAssetIds": []`

- **Component:** `basyx.aas.adapter.json.AASToJsonEncoder` (`_entity_to_json`)
- **Class / severity:** Bug / Medium - every AASX with a HierarchicalStructures Entity fails JSON schema
  validation (aas-test-engines).
- **Reproduction:**

  ```python
  json.dumps(model.Entity("Node", model.EntityType.CO_MANAGED_ENTITY), cls=AASToJsonEncoder)
  # {"idShort": "Node", "modelType": "Entity", "entityType": "CoManagedEntity", "specificAssetIds": []}
  ```

- **Expected:** omit empty lists; the V3.0.6/V3.2.0 schema has `Entity.specificAssetIds` `minItems: 1`.
  `AssetInformation` already omits them.
- **Code:** `adapter/json/json_serialization.py:711-712` (`if obj.specific_asset_id is not None` - a
  ConstrainedList is never None).
- **Upstream:** [basyx-python-sdk#636](https://github.com/eclipse-basyx/basyx-python-sdk/issues/636) (open).
- **Workaround:** `_strip_empty_specific_asset_ids` post-processes the package
  (`services/vf_common/src/vf_common/aas/aasx.py:43, 73`, O15).

<a id="bsp-02"></a>

### BSP-02 `KeyTypes` lacks `Identifiable` and `Referable`

- **Component:** `basyx.aas.model.KeyTypes`, JSON/XML deserialisation
- **Class / severity:** Bug / Medium - schema-valid models cannot be read (strict mode: unhandled `KeyError`).
- **Reproduction:** `read_aas_json_file(..., failsafe=False)` on MaintenanceInstructions 1.0 → `Error while trying
  to convert JSON object into SubmodelElementCollection: 'Identifiable'` (semanticId
  `{"type": "ModelReference", "keys": [{"type": "Identifiable", ...}]}`).
- **Expected:** `KeyTypes` of Part 1 V3.0 contains `Identifiable` and `Referable` (JSON schema V3.0.6 and V3.2.0
  enum; also aas-test-engines `test_cases/v3_0/model.py:223`); AASd-123 lists `Identifiable` among
  AasIdentifiables.
- **Code:** `model/base.py:67-150` (enum without IDENTIFIABLE/REFERABLE), `adapter/_generic.py:67-140`.
- **Upstream:** not found; submodel-templates#245 reports the symptom as a template error.
- **Workaround:** the element's semanticId is overridden in the asset data (`aas/data/assets/GR01.yaml:124`, O11).

<a id="bsp-03"></a>

### BSP-03 `AASXWriter.write_aas()` omits CDs referenced by ExternalReference semanticIds

- **Component:** `basyx.aas.adapter.aasx.AASXWriter.write_aas`
- **Class / severity:** Usability / Medium - IDTA templates use ExternalReference semanticIds, so packages written
  with the convenience API contain no concept descriptions at all.
- **Reproduction:** store with a CD `urn:x:cd:p` and a Property whose semanticId is
  `ExternalReference/GlobalReference urn:x:cd:p` → `write_aas("urn:x:aas", store, files, write_json=True)` →
  `aasx/data.json` has no `conceptDescriptions`.
- **Expected:** resolve CDs whose id equals the (single-key) semanticId value regardless of reference type, at
  least optionally.
- **Code:** `adapter/aasx.py` `write_aas` (`if isinstance(semantic_id, model.ExternalReference): continue`).
- **Upstream:** [#234](https://github.com/eclipse-basyx/basyx-python-sdk/issues/234) closed as by design
  (ModelReference = resolvable); spec background: metamodel #350.
- **Workaround:** explicit object set via `write_all_aas_objects`
  (`services/vf_common/src/vf_common/aas/aasx.py:42`, O16).

---

## 3. AAS specifications

<a id="aas-01"></a>

### AAS-01 Part 2: encoding and matching of the `semanticId` query parameter undefined

- **Spec:** Part 2 API V3.0.4 and V3.2.0, `Part2-API-Schemas` `components/parameters/SemanticId`: "The value of
  the semantic id reference (BASE64-URL-encoded)".
- **Class / severity:** Spec gap / Medium - implementations differ (BaSyx Go: base64url Reference JSON, exact
  match - BSG-02); the reference type (ModelReference vs ExternalReference) of IDTA templates varies (SMT-X-02).
- **Expected:** state that the parameter is the JSON serialisation of a Reference, and the matching strategy
  (exact / value matching, reference type significant or not).
- **Upstream:** [aas-specs-api#342](https://github.com/admin-shell-io/aas-specs-api/issues/342) (open, same
  questions); aas-specs-api#2 (closed 2022).

<a id="aas-02"></a>

### AAS-02 Part 2: servers need not validate metamodel constraints on write

- **Spec:** Part 2 V3.2.0 `http-rest-api.adoc`: validation is only recommended for bulk requests; the JSON schema
  does not encode AASd-117/AASd-120.
- **Class / severity:** Spec gap / Medium - conformant servers store invalid models (BSG-03), the problem
  surfaces in other tools.
- **Expected:** a normative statement (400 for constraint violations, or a validation profile).
- **Upstream:** [aas-specs-api#112](https://github.com/admin-shell-io/aas-specs-api/issues/112) (open, schema part).

<a id="aas-03"></a>

### AAS-03 Part 4: `ANONYMOUS` undefined for requests that carry a token

- **Spec:** IDTA-01004 V3.1 `access-rule-model.adoc`: "ANONYMOUS - Anonymous access, i.e., the request does not
  contain an access token."
- **Class / severity:** Spec gap / Low - it is open whether rules for ANONYMOUS also grant authenticated callers
  (BaSyx: yes, BSG-15). Both readings are useful; the spec should say which, or offer both.
- **Upstream:** not found.

<a id="aas-04"></a>

### AAS-04 No way to identify a batch without an AAS of its own

- **Spec:** Part 1 V3.0 AASd-014 (CoManagedEntity has neither globalAssetId nor specificAssetIds); AssetKind has
  no batch.
- **Class / severity:** Spec gap / Low - as-built BoMs that record component lots (DPP, traceability) need a
  project-specific statement.
- **Workaround:** CoManagedEntity with statement `BatchId` and a generated CD; supplier batches with an AAS are
  SelfManagedEntities (`aas/data/blueprints/workpiece_instance.yaml:146-160`, O39).
- **Upstream:** [aas-specs-metamodel#483](https://github.com/admin-shell-io/aas-specs-metamodel/issues/483)
  "AssetKind: add Batch" (closed); template side: SMT-HS-02.

<a id="aas-05"></a>

### AAS-05 No standard change-event interface

- **Spec:** Part 2 V3.2.0 has no event/notification interface.
- **Class / severity:** Spec gap / Low - every server has its own events (BaSyx: CloudEvents on MQTT/Kafka/AMQP).
- **Upstream:** aas-specs-api [#41](https://github.com/admin-shell-io/aas-specs-api/issues/41),
  [#297](https://github.com/admin-shell-io/aas-specs-api/issues/297),
  [#557](https://github.com/admin-shell-io/aas-specs-api/issues/557),
  [#600](https://github.com/admin-shell-io/aas-specs-api/issues/600) (open).

<a id="aas-06"></a>

### AAS-06 No standard way to bind an Operation to its implementation

- **Spec:** Part 2 defines `invoke`/`invoke-async`, Part 1 the Operation element; how a repository finds the code
  behind an Operation is not specified.
- **Class / severity:** Spec gap / Low - models carrying the BaSyx qualifier `invocationDelegation` work only on
  BaSyx; without it BaSyx answers 501.
- **Workaround:** custom LineControl template with `invocationDelegation` qualifiers (ADR-0017).
- **Upstream:** not found.

---

## 4. IDTA submodel templates

### 4.1 Cross-template

<a id="smt-x-01"></a>

#### SMT-X-01 Cardinality qualifier: 4 type spellings, 5 non-standard values

- **Class / severity:** Template defect / Medium - every template consumer needs alias tables.
- **Evidence** (expected: type `SMT/Cardinality`, semanticId `https://admin-shell.io/SubmodelTemplates/Cardinality/1/0`,
  values One, ZeroToOne, ZeroToMany, OneToMany):

  | Template | Deviation |
  |---|---|
  | AssetInterfacesDescription 1.1 | type `Cardinality` (759×); values `ZerotoMany` (8×), `ZerotoOne` (3×) |
  | PowerDriveTrainSizing 1.0, TimeSeries 1.1 | type `Cardinality` (216×, 52×) |
  | ContactInformations 1.0, SimulationModels 1.0, SoftwareNameplate 1.0 | type `Multiplicity` (36×, 69×, 73×, some as ConceptQualifier) |
  | ControlComponentType 2.0 | type `SMT/SMT/Cardinality`, semanticId `.../SubmodelTemplates/SMT/SMT/Cardinality/1/0` (22×) |
  | Models3D 1.0 | value `Three` (`NormOrientationVector`, 2×) |
  | CapabilityDescription 1.0 | values `TwoToMany` (`CapabilityComposedOf`), `Recursive` (SMT-CAP-01) |

- **Upstream:** [#159](https://github.com/admin-shell-io/submodel-templates/issues/159) (qualifier kind, open),
  [#279](https://github.com/admin-shell-io/submodel-templates/issues/279) (MaintenanceInstructions spellings, open).
- **Workaround:** `CARDINALITY_ALIASES` and suffix match in `services/vf_common/src/vf_common/aas/instantiate.py:250-263`.

<a id="smt-x-02"></a>

#### SMT-X-02 Submodel semanticId as (mostly dangling) ModelReference

- **Class / severity:** Template defect / Medium - semanticId queries with an ExternalReference miss these
  submodels (BSG-02); tools must try both forms.
- **Evidence:** 21 of 30 templates use `{"type": "ModelReference", "keys": [{"type": "Submodel", "value": ...}]}`
  (AID 1.1, AssetLocation, CapabilityDescription, ContactInformations, Control Component Type/Instance,
  DataRetentionPolicies, DppMetadata, FunctionalSafety, HandoverDocumentation 2.0, HierarchicalStructures 1.1,
  MaintenanceInstructions, Models3D, PowerDriveTrainSizing, ProcessVariablesForManufacturingKPICalculation,
  ProductionCalendar, Reliability, SimulationModels, SoftwareNameplate, TechnicalData 2.0, TimeSeries 1.1); in 16
  of them the key value is not even the template's own id, so the reference resolves to nothing (e.g. AID: semanticId `.../AssetInterfacesDescription/1/1/Submodel`,
  template id `.../SubmodelTemplate/AssetInterfacesDescription/1/1`). The other 9 (Nameplate 3.0, CarbonFootprint,
  AIMC 2.0, ...) use ExternalReference/GlobalReference. Element CDs are referenced as ModelReference/ConceptDescription
  in CompanyData (1×) and PowerDriveTrainSizing (10×).
- **Expected:** ExternalReference/GlobalReference for semantic ids of instances (a ModelReference must point to an
  existing model element).
- **Upstream:** [#224](https://github.com/admin-shell-io/submodel-templates/issues/224),
  [#209](https://github.com/admin-shell-io/submodel-templates/issues/209) (open).
- **Workaround:** queries in both forms (`aid.py:161-166`); semanticIds kept verbatim to stay template-conformant.

<a id="smt-x-03"></a>

#### SMT-X-03 Whitespace inside identifiers

- **Class / severity:** Template defect / Medium - CD lookup and semantic matching fail silently.
- **Evidence:**

  | Template | Element | Value |
  |---|---|---|
  | AssetLocation 1.0 | Latitude, Longitude, GeographicCoordinates, AreaRecords/Time, LocationRecords/Speed | `" 0173-1#02-ABH960#002"`, `" 0173-1#02-ABH961#002"`, `" 0173-1#02-ABH934#002"`, `" 0173-1#02-ABF198#002"`, `" 0173-1#02-AAV544#004"` |
  | PowerDriveTrainSizing 1.0 | 3× ManufacturerOrderCode; CD FrequencyAtMaxSpeed unit | `" 0173-1#02-AAO227#002"`; unit `"Hz "` |
  | TimeSeries 1.1 | LinkedSegment/EndTime | `"https://admin-shell.io/idta/TimeSeries/Segment/EndTime/1/1 "` (the CD has no space) |
  | AID 1.1 | OPC UA `uav_securityMode`, `opcua_authentication_sc` (semanticIds **and** CD ids) | `"http://opcfoundation.org/UA/WoT-Binding/securityMode "`, `".../OPCUASecurityAuthenticationScheme "` |
  | ContactInformations 1.0, SoftwareNameplate 1.0 | TypeOfCommunication | `"https://admin-shell.io/zvei/nameplate/1/0/ ContactInformations/..."` |
  | CompanyData 1.0 | DocumentationURI (semanticId and CD id) | `".../CompanyData/DocumentationURI /1/0"` |
  | TechnicalData 2.0 | 2 supplementalSemanticIds | `"https://api.eclass-cdp.com/ 0173-1-02-ABK161-002/..."` |

- **Upstream:** [#210](https://github.com/admin-shell-io/submodel-templates/issues/210) (TypeOfCommunication, open);
  #128 and #129 were closed in 2025, the SMT repository still serves the blanks.
- **Workaround:** semanticId keys are trimmed on instantiation (`instantiate.py:116`, O11).

<a id="smt-x-04"></a>

#### SMT-X-04 SubmodelElementList children carry an idShort (AASd-120)

- **Class / severity:** Template defect / Low - strict validators reject instances that copy the template.
- **Evidence:** 54 list children: AID 1.1 (22, e.g. `security/definesSecurityScheme`), CompanyData (9),
  DBP-Circularity (9), CapabilityDescription (4), AIMC 2.0 (3, `MappingConfiguration`, `Source`, `Sink`),
  MaintenanceInstructions (3), DBP-MaterialComposition (3), DppMetadata (1).
- **Upstream:** [#245](https://github.com/admin-shell-io/submodel-templates/issues/245) (MaintenanceInstructions only).
- **Workaround:** idShorts of list children are dropped (`instantiate.py:240`).

<a id="smt-x-05"></a>

#### SMT-X-05 Semantic ids without concept description in the SMT repository

- **Class / severity:** Template defect / Medium - no definitions, units or data types for these elements.
- **Evidence** (element semanticIds not among the 2 846 CDs of the repository):

  | Template | IRIs | ECLASS/IEC IRDIs | Examples |
  |---|---|---|---|
  | AssetLocation 1.0 | 21 | 20 | `.../idta/sml/addresses/1/0`, `.../idta/prop/areaid/1/0`, Latitude/Longitude |
  | PowerDriveTrainSizing 1.0 | 11 | 7 | `.../PowerDriveTrainSizing/Fan/1/0`, `.../RotraryTable/1/0` |
  | DBP-MaterialComposition 1.0 | 21 | 0 | all `...material_composition:1.0.1#...` (template id says 1.0.0) |
  | Nameplate 3.0 | 4 | 4 | `https://admin-shell.io/SMT/General/ArbitraryProp` |
  | TimeSeries 1.1 | 4 | 0 | `https://sample.com/AccelerationX/1/1` (example record left in the template) |
  | Control Component 2.0 | 2 | 0 | `.../ControlComponent/Skill/ErrorReference/2/0`, `.../SkillReference/2/0` |
  | CarbonFootprint 1.0 | 2 | 0 | GoodsHandoverAddress (`.../ContactInformations/AddressInformation`), ArbitraryContent |
  | AID 1.1 | 2 | 0 | `http://www.w3.org/2022/wot/iolink#...` |
  | ContactInformations 1.0, SoftwareNameplate 1.0, TechnicalData 2.0, MaintenanceInstructions 1.0, DBP-Circularity | 1 each | MI: 1 | `.../IPCommunication/` (trailing slash), `.../ReleaseInformation`, `.../referencenameofmanintainance/1/0` |

  Plus TimeSeries UtcTime (SMT-TS-01) and HierarchicalStructures Node (SMT-HS-01, CD exists but wrong).
- **Upstream:** [#142](https://github.com/admin-shell-io/submodel-templates/issues/142) (HS Node, open); others not found.
- **Workaround:** CDs derived from the template element plus `TEMPLATE_UNITS`
  (`services/vf_common/src/vf_common/aas/environment.py:42, 94-108`).

<a id="smt-x-06"></a>

#### SMT-X-06 Concept description quality

- **Class / severity:** Template defect / Low.
- **Evidence** (1 042 CDs referenced by the 30 templates):
  - IEC 61360 data specification id in four spellings: `http://.../DataSpecificationIEC61360/3/0` (383),
    `https://.../DataSpecificationIec61360/3/0` (352), `https://.../DataSpecificationIEC61360/3/0` (255),
    `https://.../DataSpecificationIec61360/3` (12). Part 3a V3.1 accepts the first three as deprecated and asks for
    `.../Iec61360/3`.
  - 27 CDs (IEC 61987 / IEC 62683 IRDIs, e.g. Reliability `0112/2///62683#ACE061#001`) name **their own IRDI** as
    `dataSpecification` instead of the IEC 61360 template.
  - 741 CDs without `dataType` (AASc-3a-004 does not apply only because `category` is unset), e.g. TimeSeries
    `Segment/StartTime`, ExecutedProcesses `ProcessStartTime`.
  - AssetLocation `prop/course`, `headingaccuracy`, `magneticheading`, `trueheading`: INTEGER_COUNT with unit `°`
    (should be REAL_MEASURE).
- **Workaround:** none needed (we only read preferred names, definitions, units).

<a id="smt-x-07"></a>

#### SMT-X-07 One-character idShorts invalid from metamodel V3.1

- **Class / severity:** Template defect / Low - valid in V3.0, but AASd-002 requires two characters from V3.1
  (`^[a-zA-Z][a-zA-Z0-9_-]*[a-zA-Z0-9_]+$`); BaSyx Go (V3.2) imports them with warnings.
- **Evidence:** AssetLocation 1.0 `X`, `Y`, `Z` (7×), Models3D 1.0 `X`, `Y`, `Z` (15×).
- **Upstream:** [#272](https://github.com/admin-shell-io/submodel-templates/issues/272),
  [#273](https://github.com/admin-shell-io/submodel-templates/issues/273) (open).
- **Workaround:** kept (V3.0 output, ADR-0011).

### 4.2 Asset Interfaces Description 1.1 (IDTA 02017-1-1, `https://admin-shell.io/idta/AssetInterfacesDescription/1/1/Submodel`)

<a id="smt-aid-01"></a>

#### SMT-AID-01 `enum` lists without `valueTypeListElement`

- **Class / severity:** Template defect / Medium - basyx-python-sdk refuses the template (strict); AASd-109.
- **Evidence:** 24 SubmodelElementLists `.../properties/property_name/enum`, `.../items/enum` (all six
  protocols) with `typeValueListElement: Property` and no `valueTypeListElement`. SDK: `type_value_list_element=
  Property, but value_type_list_element is not set! (Constraint AASd-109)`.
- **Upstream:** [#323](https://github.com/admin-shell-io/submodel-templates/issues/323) (open, item 1).
- **Workaround:** `_fix_list_value_type` (`instantiate.py:266-270`).

<a id="smt-aid-02"></a>

#### SMT-AID-02 No template structure for actions and events

- **Class / severity:** Template gap / Medium - every implementer invents the structure of action input/output,
  `synchronous`, event `data` and their forms.
- **Evidence:** in all six interface templates (BACnet, HTTP, IO-Link/Profinet REST, Modbus, MQTT, OPC UA)
  `InteractionMetadata.actions` and `.events` are empty collections; only `properties.property_name` is modelled.
- **Workaround:** actions and events modelled after W3C WoT TD 1.1 (`input`, `output`, `synchronous`, `forms`
  with `op`) in `services/provisioner/src/provisioner/interfaces.py:80-125` (ADR-0020).
- **Upstream:** not found (#186 asks about arrays of complex structures).

<a id="smt-aid-03"></a>

#### SMT-AID-03 One `forms` per affordance; no acknowledgement/response topic

- **Class / severity:** Template gap / Medium - asynchronous commands over MQTT (command topic + acknowledgement
  topic) cannot be described.
- **Evidence:** `forms` is one SubmodelElementCollection (cardinality One); W3C WoT TD 1.1 allows several forms per
  affordance, told apart by `op` (`invokeaction`, `queryaction`, ...). The MQTT binding terms (`mqv_retain`,
  `mqv_controlPacket`, `mqv_qos`) have no response topic; `additionalResponses` has no target.
- **Workaround:** sibling collection `ackForms` (same semanticId `td#hasForm`, `op` = `queryaction`) - O36,
  ADR-0020.
- **Upstream:** not found (the missing response-topic term belongs to the W3C WoT MQTT binding).

<a id="smt-aid-04"></a>

#### SMT-AID-04 Boolean binding terms typed `xs:string`

- **Class / severity:** Template defect / Low.
- **Evidence:** `mqv_retain` (MQTT), `modv_zeroBasedAddressing`, `modv_mostSignificantByte` (Modbus) are
  `xs:string`; the WoT bindings define them as boolean.
- **Workaround:** values written as `"true"`/`"false"`.

### 4.3 Asset Location 1.0 (`https://admin-shell.io/idta/smt/assetlocation/1/0`)

<a id="smt-al-01"></a>

#### SMT-AL-01 Leading spaces in IRDIs, 41 semantic ids without CD, no units for coordinates

- **Class / severity:** Template defect / Medium - geographic coordinates have no unit or definition anywhere.
- **Evidence:** see SMT-X-03 (5 leading spaces) and SMT-X-05 (21 IRIs + 20 IRDIs without CD); Latitude/Longitude
  (`0173-1#02-ABH960#002`, `0173-1#02-ABH961#002`, `xs:double`) have no CD, hence no unit (°).
- **Workaround:** trimmed keys; generated CDs with unit ° (`environment.py:42`).
- **Upstream:** #224 (submodel semanticId only).

<a id="smt-al-02"></a>

#### SMT-AL-02 idShort typo `AreaDesciption`

- **Class / severity:** Template defect / Low - `VisitedAreas[]/AreaDesciption` (semanticId `.../mlp/areadescription/1/0`).

### 4.4 Capability Description 1.0 (`https://admin-shell.io/idta/SubmodelTemplate/CapabilityDescription/1/0`)

<a id="smt-cap-01"></a>

#### SMT-CAP-01 Duplicate `SMT/Cardinality` qualifier (AASd-021)

- **Class / severity:** Template defect / Medium - basyx-python-sdk refuses the template (strict).
- **Evidence:** `PropertySubmodelList` and its nested `PropertySubmodelList` carry `SMT/Cardinality = ZeroToMany`
  **and** `SMT/Cardinality = Recursive` (semanticId `https://admin-shell.io/SubmodelTemplates/Recursion/1/0`) - the
  recursion qualifier has the wrong type. SDK: `Object with attribute (name='type', value='SMT/Cardinality') is
  already present (Constraint AASd-021)`.
- **Workaround:** template qualifiers are removed on instantiation (`instantiate.py:114`).

<a id="smt-cap-02"></a>

#### SMT-CAP-02 Inconsistent PropertyRange semanticIds, string Range

- **Class / severity:** Template defect / Low.
- **Evidence:** `PropertyContainer/PropertyRange` uses `.../CapabilityPropertyEnumType/Range/1/0`, the same element
  inside `PropertySubmodelList` `.../CapabilityPropertyType/Range/1/0` (both CDs exist); both Ranges are
  `xs:string`; the list `PropertySubmodelList` mixes Range, Property, MLP and SML (`typeValueListElement:
  SubmodelElement`).

### 4.5 Control Component 2.0 (Type `.../ControlComponent/Type/2/0`, Instance `.../ControlComponent/Instance/2/0`)

<a id="smt-cc-01"></a>

#### SMT-CC-01 No skill → endpoint relation

- **Class / severity:** Template gap / Medium - a client cannot find out which endpoint executes a skill.
- **Evidence:** `Skills.Skill` has `Disabled`, `Modes`, `Parameters`, `Errors`, `Uses` (skill → skill only);
  `Endpoints.Endpoint` relates to AID interfaces only.
- **Workaround:** extension `UsesEndpoints` (SML of ReferenceElements) per skill
  (`aas/data/common/control_uses_endpoints.yaml`, ADR-0020, O36).
- **Upstream:** [#214](https://github.com/admin-shell-io/submodel-templates/issues/214) (open, same question).

<a id="smt-cc-02"></a>

#### SMT-CC-02 Qualifier `SMT/SMT/Cardinality`; CDs missing

- **Class / severity:** Template defect / Low - see SMT-X-01 (Type template) and SMT-X-05 (ErrorReference,
  SkillReference).

### 4.6 Carbon Footprint 1.0 (`https://admin-shell.io/idta/CarbonFootprint/CarbonFootprint/1/0`)

<a id="smt-pcf-01"></a>

#### SMT-PCF-01 No data-quality, primary-data or assurance elements

- **Class / severity:** Template gap / Medium - PACT/Catena-X exchange requires primary data share, data quality
  indicators and assurance; the template can only carry the value, methods, phases and dates.
- **Evidence:** `ProductCarbonFootprints[]`: PcfCalculationMethods, PcfCO2eq, ReferenceImpactUnitForCalculation,
  QuantityOfMeasureForCalculation, LifeCyclePhases, ExplanatoryStatement, GoodsHandoverAddress, PublicationDate,
  ExpirationDate - nothing else.
- **Workaround:** extra properties `PrimaryDataShare`, `SupplierSpecificDataShare`, `BatchId`
  (`services/supplier/src/supplier/batch_aas.py:79`, O61).
- **Upstream:** not found (#314 discusses generic vs. battery PCF semanticIds).

### 4.7 Hierarchical Structures enabling BoM 1.1 (`https://admin-shell.io/idta/HierarchicalStructures/1/1/Submodel`)

<a id="smt-hs-01"></a>

#### SMT-HS-01 Node description and CD copied from EntryNode

- **Class / severity:** Template defect / Low - every node of a BoM carries "Base entry point for the Entity tree
  in this Submodel, this must be a Self-managed Entity reflecting the Asset" and displayName "Node".
- **Evidence:** `EntryNode/Node` description = EntryNode description; CD `https://admin-shell.io/idta/
  HierarchicalStructures/Node/1/0` definition = EntryNode definition (the nested `Node/Node` has the right text:
  "Can be a Co-managed or Self-managed entity...").
- **Workaround:** Entities are named after their asset, template texts dropped
  (`services/vf_common/src/vf_common/aas/entities.py`, `instantiate.py:215-217`).
- **Upstream:** related [#142](https://github.com/admin-shell-io/submodel-templates/issues/142) (Node CD).

<a id="smt-hs-02"></a>

#### SMT-HS-02 No batch/lot concept for as-built BoMs

- **Class / severity:** Template gap / Low - see AAS-04; the template has BulkCount but no lot/batch statement.
- **Workaround:** statement `BatchId` + SameAs to the type BoM node (O39).

### 4.8 Maintenance Instructions 1.0 (`https://admin-shell.io/idta/SubmodelTemplate/MaintenanceInstructions/1/0`)

<a id="smt-mi-01"></a>

#### SMT-MI-01 semanticId is a ModelReference with key type `Identifiable`

- **Class / severity:** Template defect / Medium - the reference points to no model element; basyx-python-sdk
  crashes on it (BSP-02).
- **Evidence:** `MaintenanceInstructionsForSpecificInterval__00__/BasicMaintenanceInformation` semanticId
  `{"type": "ModelReference", "keys": [{"type": "Identifiable", "value": "https://admin-shell.io/idta/
  maintenanceinstructions/basicmaintenanceinformation/1/0"}]}` (a CD with this id exists).
- **Expected:** ExternalReference/GlobalReference like the other elements.
- **Upstream:** [#245](https://github.com/admin-shell-io/submodel-templates/issues/245) (open, item 1).
- **Workaround:** `_semanticId` override in the asset data (`aas/data/assets/GR01.yaml:124`, `CV01.yaml`,
  `UR5E_TYPE.yaml`).

<a id="smt-mi-02"></a>

#### SMT-MI-02 Misspelled and duplicated semanticIds and idShorts

- **Class / severity:** Template defect / Low.
- **Evidence:**
  - `MaintenanceSparePartList/MaintenanceSparePart` semanticId **and CD id** `htthttps://admin-shell.io/idta/
    maintenanceinstructions/maintenancesparepart/1/0`.
  - Consumables `ReferenceNameOfMaintenance` semanticId `.../referencenameofmanintainance/1/0` (no CD); everywhere
    else `ReferenceToMaintenanceID` reuses the semanticId `.../referencenameofmaintenance/1/0` of
    `ReferenceNameOfMaintenance`.
  - `CollectionQuantityOfSparepartForSpecificInterval__00__` contains `ReferenceNameOfMaintenance` and
    `ReferenceNameOfMaintenance__01__` (AASd-022 per #245); `Sparepart` vs `SparePart`.
- **Upstream:** #245, [#279](https://github.com/admin-shell-io/submodel-templates/issues/279) (open, partial).
- **Workaround:** kept verbatim (template-conformant); unused elements pruned.

### 4.9 Process Parameters 1.0 and Executed Processes 1.0

<a id="smt-pp-01"></a>

#### SMT-PP-01 ProcessParameters id and semanticId use `https://admin-shell-io/...`

- **Class / severity:** Template defect / Medium - the template id and the submodel semanticId are
  `https://admin-shell-io/idta/SubmodelTemplate/ProcessParameters/1/0` (host `admin-shell-io`); consumers that
  match the obviously intended `admin-shell.io` IRI miss every instance.
- **Workaround:** kept verbatim (`tools/fetch_idta_templates.py`, O11).
- **Upstream:** not found.

<a id="smt-ep-01"></a>

#### SMT-EP-01 ExecutedProcesses start/end times typed `xs:string`

- **Class / severity:** Template defect / Low - `ProcessStartTime`, `ProcessEndTime`, `ProcessStages/.../StartTime`,
  `EndTime` are `xs:string` (CDs without dataType); timestamps should be `xs:dateTime`. Template id and semanticId
  `https://admin-shell.io/idta/ExecutedProcesses/1/0` do not follow the `.../SubmodelTemplate/...` id scheme of
  the other templates.
- **Workaround:** ISO 8601 strings written into the string properties.

### 4.10 Time Series Data 1.1 (IDTA 02008-1-1, `https://admin-shell.io/idta/TimeSeries/1/1`)

<a id="smt-ts-01"></a>

#### SMT-TS-01 No concept descriptions for the time semantics

- **Class / severity:** Template defect / Medium - the semantic ids that select the time scale of a record are
  not resolvable.
- **Evidence:** IDTA 02008-1-1 Table 4/Table 10 name `https://admin-shell.io/idta/TimeSeries/UtcTime/1/1`,
  `.../TaiTime/1/1`, `.../RelativePointInTime/1/1`, `.../RelativeTimeDuration/1/1`; of these the repository
  publishes only `RelativePointInTime`.
- **Workaround:** the provisioner adds a UtcTime CD with the texts of Table 10
  (`services/provisioner/src/provisioner/time_series.py:17-38`).
- **Upstream:** not found.

<a id="smt-ts-02"></a>

#### SMT-TS-02 Segment times typed `xs:string`, CD text copied

- **Class / severity:** Template defect / Low.
- **Evidence:** `StartTime`, `EndTime`, `LastUpdate` of External/Linked/InternalSegment are `xs:string`; the spec
  gives `[TIMESTAMP]` (printed "TIMESTSAMP"). The CD `Segment/StartTime/1/1` has no dataType and the description
  "Time when the stage started." (ExecutedProcesses wording); the CD definition matches the spec.
- **Workaround:** not used (LinkedSegment without times).

### 4.11 Other templates

<a id="smt-pdt-01"></a>

#### SMT-PDT-01 PowerDriveTrainSizing 1.0: idShort typos, leading-space IRDIs, ModelReference semanticIds

- **Class / severity:** Template defect / Low (template not used, O13).
- **Evidence:** idShorts `EnergyConsumtionPerCycle` (3×), `RotraryTable` (also in its semanticIds); 3 leading-space
  IRDIs and unit `"Hz "` (SMT-X-03); 10 element semanticIds as ModelReference/ConceptDescription (SMT-X-02); type
  `Cardinality` (SMT-X-01); 18 semantic ids without CD (SMT-X-05).
- **Upstream:** related [#248](https://github.com/admin-shell-io/submodel-templates/issues/248) (string Ranges, open).

<a id="smt-cd-01"></a>

#### SMT-CD-01 CompanyData 1.0: IEC 61360 `unit` used for data types

- **Class / severity:** Template defect / Low - 67 CDs put the data type into `unit` (`"STRING"`, `"Boolean"`,
  `"Date"`, `"AnyUri"`, `"PositiveInteger"`, `"GYear"`, `"langString"`, `"File"`, ...), e.g.
  `https://admin-shell.io/idta/CompanyData/IBAN/1/0`; `Turnover`, `EquityRatio`, `InvestmentVolume` are STRING.
  Plus the space in `DocumentationURI /1/0` (SMT-X-03).
- **Upstream:** not found (#266 and #267 report other CompanyData issues).

<a id="smt-ci-01"></a>

#### SMT-CI-01 ContactInformations 1.0 / SoftwareNameplate 1.0: broken TypeOfCommunication and IPCommunication ids

- **Class / severity:** Template defect / Low.
- **Evidence:** TypeOfCommunication semanticId with an inner space (SMT-X-03); `IPCommunication__00__` semanticId
  `.../ContactInformations/IPCommunication/` (trailing slash, no CD; the spec gives
  `.../ContactInformation/IPCommunication`); qualifier type `Multiplicity`.
- **Upstream:** [#206](https://github.com/admin-shell-io/submodel-templates/issues/206),
  [#210](https://github.com/admin-shell-io/submodel-templates/issues/210) (open).

---

## 5. Other tooling

<a id="ot-01"></a>

### OT-01 aas-test-engines 1.0.3 checks only ContactInformations 1.0 and Nameplate 2.0

- **Class / severity:** Usability / Low - `test_cases/v3_0/submodel_templates.py:240, 250` register only these two
  templates; for the other 29 templates in use, "passes the IDTA test engine" means metamodel conformance only.
- **Upstream:** related admin-shell-io/aas-test-engines#96 (closed).

---

## Suggested upstream issues (draft titles, ordered by value)

1. basyx-go-components: "DPP API: dppsByProductId matches globalAssetId instead of uniqueProductIdentifier" (BSG-09)
2. basyx-go-components: "Value-only $value: accept and return JSON numbers/booleans per ValueOnly encoding" (BSG-01)
3. basyx-go-components: "DPP API: representation=full fails with 422 for
   RelationshipElement/ReferenceElement/Range/Blob" (BSG-11)
4. basyx-go-components: "ABAC: denied value-only PATCH returns 500 instead of 403" (BSG-13)
5. submodel-templates: "Use ExternalReference for submodel semanticIds; replace dangling ModelReferences (21 templates)"
   (SMT-X-02, add to #224)
6. submodel-templates: "Unify cardinality qualifiers (Cardinality, Multiplicity, SMT/SMT/Cardinality, ZerotoMany, Three,
   TwoToMany, Recursive)" (SMT-X-01, add to #159)
7. basyx-python-sdk: "KeyTypes lacks Identifiable and Referable (V3.0 enum) - KeyError on valid JSON" (BSP-02)
8. submodel-templates: "Remove whitespace from identifiers in AssetLocation, AID, TimeSeries, PowerDriveTrainSizing,
   CompanyData, TechnicalData, ContactInformations, SoftwareNameplate" (SMT-X-03)
9. submodel-templates: "Control Component 2.0: relate skills to endpoints" (SMT-CC-01, comment on #214)
10. submodel-templates: "AID 1.1: template structure for actions/events and multiple forms per affordance (op), MQTT
    acknowledgement topic" (SMT-AID-02/03)
11. basyx-go-components: "ABAC: $sm formulas break DPP API reads (cannot extract alias from column submodel.id_short)" (BSG-14)
12. basyx-go-components: "DPP API: several submodels with the same semanticId - all but the newest dropped silently" (BSG-12)
13. submodel-templates: "TimeSeries 1.1: publish CDs for UtcTime/TaiTime/RelativeTimeDuration; type segment times as
    xs:dateTime" (SMT-TS-01/02)
14. submodel-templates: "CarbonFootprint: data quality, primary data share and assurance elements (PACT alignment)" (SMT-PCF-01)
15. submodel-templates: "Publish missing concept descriptions (AssetLocation 41, PowerDriveTrainSizing 18, ...)" (SMT-X-05)
16. submodel-templates: "CapabilityDescription 1.0: duplicate SMT/Cardinality qualifier (Recursive) violates AASd-021" (SMT-CAP-01)
17. submodel-templates: "ProcessParameters 1.0: template id and semanticId use admin-shell-io instead of admin-shell.io"
    (SMT-PP-01)
18. aas-specs-api: comment on #342 with the BaSyx Go behaviour and the template reference-type mix (AAS-01)
19. basyx-go-components: "No validation of metamodel constraints (AASd-021/108/109/120) on POST/PUT" (BSG-03) and
    aas-specs-api: "Normative constraint validation on write" (AAS-02)
20. basyx-go-components: "Registry integration: embedded submodel descriptors without idShort/semanticId" (BSG-06);
    "Query: limit applied before the condition" (BSG-07); "Discovery entry kept after AAS deletion" (BSG-08)
21. submodel-templates: smaller defects - HierarchicalStructures Node text (SMT-HS-01), MaintenanceInstructions typos
    (SMT-MI-02, add to #245/#279), AID boolean terms (SMT-AID-04), CompanyData units (SMT-CD-01), CD data specification
    ids (SMT-X-06), AssetLocation typo (SMT-AL-02), ExecutedProcesses times (SMT-EP-01)
22. aas-specs-security: "Define whether ANONYMOUS rules apply to requests with a token" (AAS-03)

---

## Appendix A: investigated, not upstream

| Item | Result |
|---|---|
| BaSyx omits Blob values (O19) | Spec default: `extent` defaults to `withoutBlobValue` (Part 2 `Extent` parameter). Our first retry used the wrong spelling of the value. |
| Eventing needs `BASYX_EVENTING_OUTBOX_ENABLED` and the `mqtt://` scheme | Documented (`docu/eventing/*.md`: "All three activation settings are required"; startup error `MQTT-CONFIG-SCHEME`). |
| aas-gui "publishes no version tags" (O1) | Outdated: Docker Hub has date tags such as `v2-260924` (2026-09-24, the digest we pin) besides `SNAPSHOT-*` and commit tags. |
| "BaSyx registries have no query by semanticId" (O45) | Not true for 1.1.0: `POST /query/submodel-descriptors` works (paging quirk BSG-07); our clients scan instead. |
| BaSyx matches the semanticId reference type exactly | Consistent with metamodel #350 (no equivalence of ModelReference[Submodel] and GlobalReference); the defect is in the templates (SMT-X-02). |
| AASc-3a-009 findings of aas-test-engines | Our generated CDs (measures without unit) - fixed with COUNT data types. |
| "Unit conflicts" (Width m/mm, Diameter, Repeatability, SupplyVoltage, Min/Max types) | Our asset data - fixed with per-concept names (`conceptName`). |
| Reliability MTTF in years | CD unit `y` is the IEC 62683 definition; our LB_TYPE data used hours - fixed. |
| DppMetadata granularity values `Model`/`Item` | The template is right; our brief used lowercase. |
| BaSyx forwards the caller's bearer token to the delegation target | Intended (ADR-0027); the ops gateway re-checks it. |
| DPP history (`/v1/dppsByIdAndDate`) 404 | Needs BaSyx history on the AAS environment (O40) - configuration. |
| aas-test-engines "lower-cases OPC part names" (M3 note) | Not reproducible from the 1.0.3 source (no case folding in `opc.py`/`file.py`); dropped. |
| basyx-python-sdk 2.2 validates idShorts with the V3.0 rule | Expected for a V3.0 SDK; the V3.1 rule change affects the templates (SMT-X-07). |
