"""Entry point: python -m historian (configuration via environment variables and infra/historian.json, see
docs/interfaces/services.md)."""

from __future__ import annotations

import logging
import os

from vf_common.historian import HistorianConfig, InfluxClient
from vf_common.mqtt import MqttClient
from vf_common.uns import Uns, broker_address

from .batch import BatchWriter
from .service import Historian, variable_types


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    config = HistorianConfig.load()
    influx = InfluxClient(os.environ.get("VF_INFLUX_URL", "http://localhost:8181"), config.database)
    batch = config.batch
    writer = BatchWriter(influx.write, interval_s=float(batch["interval_s"]),
                         max_lines=int(batch["max_lines"]), max_buffer=int(batch["max_buffer_lines"]))
    host, port = broker_address(os.environ.get("VF_MQTT_URL", "mqtt://localhost:1883"))
    types = variable_types()
    logging.getLogger("historian").info("recording %d devices, %d variables into database %s",
                                        len(types), sum(map(len, types.values())), config.database)
    Historian(MqttClient("vf-historian", host, port), Uns.load(), types, writer).run()


if __name__ == "__main__":
    main()
