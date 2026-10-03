"""IDTA Time Series Data 1.1 (IDTA 02008-1-1) submodel of a device, generated from its FMI model description:
the history lives in the historian (InfluxDB 3, ADR-0019) and is referenced by a LinkedSegment (Endpoint +
SQL Query); the AAS holds only the record structure and its semantics.

Metadata.Record: `Time` (UtcTime, xs:dateTime) + one Property per FMI output (idShort = variable name =
column, semanticId = the generated FMI process-value concept description with unit). No values (structure
only)."""

from __future__ import annotations

from vf_common.aas.templates import IEC61360
from vf_common.historian import HistorianConfig

from .device_models import process_value_cd_id
from .fmi import ModelDescription

# Time semantics of IDTA 02008-1-1 (Table 4 / Table 10). The IDTA SMT repository publishes no concept
# description for it, so the provisioner adds one with the texts of Table 10.
UTC_TIME = "https://admin-shell.io/idta/TimeSeries/UtcTime/1/1"
UTC_TIME_IRDI = "0112/2///61360_4#ADA387#001"


def utc_time_cd() -> dict:
    content = {"modelType": "DataSpecificationIec61360",
               "preferredName": [{"language": "en", "text": "Timestamp UTC"},
                                 {"language": "de", "text": "Zeitstempel UTC"}],
               "shortName": [{"language": "en", "text": "UtcTime"}],
               "definition": [{"language": "en", "text": "Timestamp according to ISO 8601 on the timescale "
                                                         "coordinated universal time (UTC)."},
                              {"language": "de", "text": "Zeitstempel nach ISO 8601 auf der Zeitskala der "
                                                         "koordinierten Weltzeit (UTC)."}],
               "dataType": "TIMESTAMP"}
    return {"modelType": "ConceptDescription", "id": UTC_TIME, "idShort": "UtcTime",
            "isCaseOf": [{"type": "ExternalReference",
                          "keys": [{"type": "GlobalReference", "value": UTC_TIME_IRDI}]}],
            "embeddedDataSpecifications": [{
                "dataSpecification": {"type": "ExternalReference",
                                      "keys": [{"type": "GlobalReference", "value": IEC61360}]},
                "dataSpecificationContent": content}]}


def recorded_variables(md: ModelDescription) -> list[str]:
    """Every FMI output is recorded by the historian (high-rate signals live only there, ADR-0019)."""
    return [v.name for v in md.by_causality("output")]


def time_series_values(tag: str, instance: str, md: ModelDescription, historian: HistorianConfig) -> dict:
    record = {"Time": [{"_idShort": "Time", "valueType": "xs:dateTime", "semanticId": UTC_TIME,
                        "_noValue": True, "_description": {
                            "en": "UTC timestamp of the sample (UNS ts, simulation time base); column time.",
                            "de": "UTC-Zeitstempel des Werts (UNS ts, Simulationszeitbasis); Spalte time."}}]}
    for var in md.by_causality("output"):
        record["+" + var.name] = {"valueType": var.xsd_type, "semanticId": process_value_cd_id(md, var),
                                  "_noValue": True}
    table = historian.table(instance)
    return {
        "Metadata": {
            "Name": {"en": f"Shop-floor history of {tag}", "de": f"Shop-Floor-Verlauf von {tag}"},
            "Description": {
                "en": f"All FMI outputs of {tag} as published on the UNS (on change, continuous values at "
                      "most 10 Hz), recorded by the historian with UTC timestamps. Read them with the SQL "
                      "query of the linked segment.",
                "de": f"Alle FMI-Ausgänge von {tag}, wie im UNS veröffentlicht (bei Änderung, "
                      "kontinuierliche Werte höchstens 10 Hz), vom Historian mit UTC-Zeitstempeln "
                      "aufgezeichnet. Abfrage mit der SQL-Abfrage des verknüpften Segments."},
            "Record": record},
        "Segments": {"LinkedSegment": [{
            "_idShort": "Historian",
            "Name": {"en": f"Historian table {table}", "de": f"Historian-Tabelle {table}"},
            "Description": {
                "en": f"InfluxDB 3 SQL. Endpoint: HTTP GET with the query in parameter q, or POST JSON "
                      f"{{\"db\": \"{historian.database}\", \"q\": <Query>, \"format\": \"json\"}}. Rows of "
                      "one session carry the tag 'session'.",
                "de": f"InfluxDB-3-SQL. Endpoint: HTTP GET mit der Abfrage im Parameter q oder POST JSON "
                      f"{{\"db\": \"{historian.database}\", \"q\": <Query>, \"format\": \"json\"}}. Zeilen "
                      "einer Sitzung tragen das Tag 'session'."},
            "State": "in progress",
            "Endpoint": historian.endpoint(),
            "Query": historian.linked_query(instance, recorded_variables(md))}]},
    }
