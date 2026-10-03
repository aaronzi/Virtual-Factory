# Runtime blueprints (not preloaded)

`workpiece_instance.yaml` is the reference structure of ONE workpiece (product instance) AAS that the MES creates at
runtime for every part (serial `PC3280-<YYYY>-<NNNNNN>`, derivedFrom `PC3280_TYPE`). The MES fills Nameplate, DPP
metadata, actual PCF, ExecutedProcesses (OP10-OP90), QualityInspection, the two MeasurementValue submodels and the
AssetLocation (KLT slot) per part, plus the item-level passport content (ADR-0021): as-built technical data, contacts,
as-built BoM with the component batches reported by AC01, material composition and recycled content per batch, and
the handover documents with the generated inspection certificate (sample `aas/files/docs/IC-PC3280-2026-000123.pdf`,
`uv run python -m mes.certificate`). Type data are shared with PC3280_TYPE via `common/product_passport_pc3280.yaml`.
This file shows serial `PC3280-2026-000123`. Blueprints are only validated
(`uv run -m provisioner check --only PC3280_TYPE,WP_PC3280_2026_000123 --blueprints`) and never written to the preload.
