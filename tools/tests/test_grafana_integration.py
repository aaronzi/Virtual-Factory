"""Grafana (ADR-0022) against the running compose stack (`uv run pytest -m integration`): health, anonymous
read-only access, admin/editor accounts, historian data source and a real panel query of "LINE01 live"."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import yaml

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]
GRAFANA = "http://localhost:3002"
DASHBOARD_UID = "vf-line01-live"
DATASOURCE_UID = "vf-historian"
DASHBOARD_FILE = ROOT / "infra/grafana/dashboards/line01-live.json"


def _service_env() -> dict:
    compose = yaml.safe_load((ROOT / "infra/docker-compose.yml").read_text(encoding="utf-8"))
    return compose["services"]["grafana"]["environment"]


@pytest.fixture(scope="module")
def anon():
    client = httpx.Client(base_url=GRAFANA, timeout=10)
    try:
        client.get("/api/health").raise_for_status()
    except httpx.HTTPError:
        pytest.skip("Grafana (compose stack) not running")
    yield client
    client.close()


@pytest.fixture(scope="module")
def admin(anon):
    with httpx.Client(base_url=GRAFANA, timeout=10,
                      auth=("admin", str(_service_env()["GF_SECURITY_ADMIN_PASSWORD"]))) as client:
        yield client


def test_health(anon):
    assert anon.get("/api/health").json()["database"] == "ok"


def test_anonymous_viewer_reads_the_dashboard(anon):
    response = anon.get(f"/api/dashboards/uid/{DASHBOARD_UID}")
    assert response.status_code == 200
    body = response.json()
    assert body["dashboard"]["title"] == "LINE01 live"
    assert body["meta"]["canSave"] is False and body["meta"]["canEdit"] is False
    assert anon.get("/api/org").json()["name"] == "Virtual Factory"
    assert anon.get("/api/dashboards/home").json().get("redirectUri", "").startswith(f"/d/{DASHBOARD_UID}")


def test_anonymous_save_is_refused(anon):
    dashboard = anon.get(f"/api/dashboards/uid/{DASHBOARD_UID}").json()["dashboard"]
    response = anon.post("/api/dashboards/db", json={"dashboard": dashboard, "overwrite": True})
    assert response.status_code in (401, 403), response.text[:200]


def test_admin_can_save_the_provisioned_dashboard(admin):
    """allowUiUpdates: the provisioned dashboard is saved back unchanged (content stays the repo version)."""
    body = admin.get(f"/api/dashboards/uid/{DASHBOARD_UID}").json()
    assert body["meta"]["canSave"] is True
    response = admin.post("/api/dashboards/db", json={
        "dashboard": body["dashboard"], "folderUid": body["meta"].get("folderUid", "vf"), "overwrite": True,
        "message": "integration test: unchanged save"})
    assert response.status_code == 200, response.text[:300]
    assert response.json()["status"] == "success"


def test_editor_account_has_the_editor_role(anon):
    password = str(_service_env()["VF_GRAFANA_EDITOR_PASSWORD"])
    orgs = anon.get("/api/user/orgs", auth=("editor", password)).json()
    assert {"name": "Virtual Factory", "role": "Editor"}.items() <= orgs[0].items()


def test_historian_datasource_health(admin):
    response = admin.get(f"/api/datasources/uid/{DATASOURCE_UID}/health")
    assert response.status_code == 200, response.text[:300]
    assert response.json()["status"] == "OK"


def _query(client: httpx.Client, sql: str, since: str = "now-6h") -> list[dict]:
    response = client.post("/api/ds/query", json={"from": since, "to": "now", "queries": [
        {"refId": "A", "datasource": {"uid": DATASOURCE_UID}, "rawSql": sql, "format": "table",
         "rawQuery": True}]})
    assert response.status_code == 200, response.text[:300]
    result = response.json()["results"]["A"]
    assert "error" not in result, result.get("error")
    return result.get("frames", [])


def _panel_sql(title: str) -> str:
    dashboard = json.loads(DASHBOARD_FILE.read_text(encoding="utf-8"))
    panel = next(p for p in dashboard["panels"] if p["title"] == title)
    return panel["targets"][0]["rawSql"]


def test_panel_query_returns_rows_through_grafana(anon):
    """Repo version of the 'Parts per minute' panel query, run as anonymous viewer for the latest session."""
    frames = _query(anon, "SELECT max(session) AS sid FROM plc01", since="now-7d")
    sid = frames[0]["data"]["values"][0][0] if frames and frames[0]["data"]["values"][0] else None
    if not sid:
        pytest.skip("historian has no session yet (start the Godot factory)")
    frames = _query(anon, _panel_sql("Parts per minute (OK / NOK)").replace("${sid}", sid), since="now-7d")
    names = [f["name"] for f in frames[0]["schema"]["fields"]]
    assert names == ["time", "OK", "NOK"]
    assert len(frames[0]["data"]["values"][0]) > 0
