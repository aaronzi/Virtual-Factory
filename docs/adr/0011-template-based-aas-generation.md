# ADR-0011: Template-based AAS generation from vendored IDTA templates

- Status: accepted
- Date: 2026-10-03

## Context
About 25 AAS with roughly 200 submodels must follow the IDTA submodel templates exactly (structure, semantic IDs,
cardinalities) and stay maintainable. Hand-written JSON or SDK object code would drift from the templates and is hard
to review.

## Decision
- The IDTA templates and their concept descriptions are **vendored** from the IDTA SMT repository (an AAS API server)
  by `tools/fetch_idta_templates.py` into `aas/templates/idta` (with a manifest of versions and semantic IDs).
- A JSON-level **instantiation engine** (`vf_common.aas.instantiate`) fills a template from plain YAML data keyed by
  idShort:
  - expands placeholders and lists
  - removes unfilled optional elements and reports unfilled mandatory ones (MISSING) and keys outside the template
    (UNKNOWN)
  - resolves references in a second pass
  - strips template qualifiers and records `administration.templateId`
  - expands SMT drop-ins (AddressInformation)
- **Custom templates** are written in a compact YAML DSL (`aas/templates/custom`) and compiled to the same template
  format plus IEC 61360 concept descriptions (en/de preferred name and definition, unit, data type), so custom
  submodels have the same quality as IDTA ones.
- Output is validated strictly with basyx-python-sdk and the IDTA `aas-test-engines`, then packaged as one AASX per
  AAS.
- JSON level instead of SDK objects: a few upstream templates are not strictly valid as templates (a missing
  `valueTypeListElement`, duplicate qualifiers, one malformed element). The engine fixes or prunes these during
  instantiation, and the *output* is strictly validated.

## Consequences
+ The data files stay small and readable; the templates are the single source of structure, and template updates are
  a re-fetch.
+ Every build reports conformance gaps (MISSING/UNKNOWN) instead of silently producing partial models.
− The engine has to handle template quirks (qualifier spellings, placeholders); these are covered by unit tests.
− V3.0 output: some IDTA templates contain idShorts that the V3.1+ rules disallow (e.g. `X`, `Y`, `Z` in AssetLocation).
  BaSyx Go (V3.2) imports them with warnings.
