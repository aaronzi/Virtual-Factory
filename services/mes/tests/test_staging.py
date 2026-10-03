"""Line-side staging reports of new component lots to the ERP (ADR-0028): once per lot, off the BPMN task
thread, repeated after a failure."""

from __future__ import annotations

import json
import time

import httpx

from mes.staging import LotStaging


def _wait(staging: LotStaging, count: int) -> None:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and (staging._pending or len(staging._reported) < count):
        time.sleep(0.01)


def test_each_lot_is_reported_once_and_failures_are_repeated():
    posted, fail = [], {"DTS-2608-1174"}

    def erp(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        posted.append(body["lot"])
        status = 503 if body["lot"] in fail else 201
        return httpx.Response(status, json={"MaterialLotID": body["lot"]})

    staging = LotStaging("http://erp")
    staging.http = httpx.Client(transport=httpx.MockTransport(erp))
    staging.report("SealKit=DTS-2608-1173;Barrel=L2609-0419")
    staging.report("SealKit=DTS-2608-1173;Barrel=L2609-0419;Unknown=x")
    _wait(staging, 2)
    assert sorted(posted) == ["DTS-2608-1173", "L2609-0419"]
    assert ("5032-1006", "DTS-2608-1173") in staging._reported
    staging.report("SealKit=DTS-2608-1174")
    _wait(staging, 2)
    fail.clear()
    staging.report("SealKit=DTS-2608-1174")  # next part of the lot: reported again
    _wait(staging, 3)
    assert posted.count("DTS-2608-1174") == 2 and ("5032-1006", "DTS-2608-1174") in staging._reported


def test_without_erp_nothing_is_reported():
    staging = LotStaging(None)
    staging.report("SealKit=DTS-2608-1173")
    assert staging._queue.empty()
