# Runtime blueprints (not preloaded)

`workpiece_instance.yaml` is the reference structure of ONE workpiece (product instance) AAS that the MES creates at
runtime for every part (serial `PC3280-<YYYY>-<NNNNNN>`, derivedFrom `PC3280_TYPE`). The MES fills Nameplate, DPP
metadata, actual PCF, ExecutedProcesses (OP10-OP90), QualityInspection, the two MeasurementValue submodels and the
AssetLocation (KLT slot) per part; this file shows serial `PC3280-2026-000123`. Blueprints are only validated
(`uv run -m provisioner check --only PC3280_TYPE,WP_PC3280_2026_000123 --blueprints`) and never written to the preload.
