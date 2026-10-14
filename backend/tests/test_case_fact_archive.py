"""Only verified facts from a linked, resolved Case enter the long-term device view."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from serviceos_api.bootstrap_local import seed_local_accounts
from serviceos_api.main import create_app
from serviceos_api.settings import Settings


@pytest.fixture
def app(database_engine):
    with Session(database_engine) as session:
        seed_local_accounts(session)
    return create_app(database_engine=database_engine, settings=Settings(
        environment="test", auth_mode="local", local_password="test-only-password",
    ))


def login(app, username):
    client = TestClient(app)
    response = client.post("/api/v1/local-auth/login", json={"username": username,
                           "password": "test-only-password"})
    assert response.status_code == 200, response.text
    return client


def test_case_fact_requires_link_verification_resolution_and_can_retract(app):
    customer = login(app, "customer-a")
    other = login(app, "customer-b")
    staff = login(app, "staff")
    device = customer.post("/api/v1/devices", json={"model": "A3134"}).json()
    case = customer.post("/api/v1/cases", json={"problem_text": "端口接触不良"}).json()
    base = f"/api/v1/devices/{device['id']}"
    candidate_body = {"expected_device_revision": 1, "client_fact_id": str(uuid4()), "fact_key": "port_type",
                      "value": "USB-C", "source_case_id": case["id"]}
    assert other.post(base + "/facts", json=candidate_body).status_code == 404
    assert customer.post(base + "/facts", json=candidate_body).status_code == 409
    linked = customer.post(f"/api/v1/cases/{case['id']}/devices", json={
        "device_id": device["id"], "expected_version": 1,
    })
    assert linked.status_code == 200, linked.text
    case = linked.json()
    candidate = customer.post(base + "/facts", json=candidate_body)
    assert candidate.status_code == 201, candidate.text
    fact = candidate.json()
    assert customer.post(base + "/facts", json=candidate_body).json()["id"] == fact["id"]
    assert customer.post(base + "/facts", json=candidate_body | {"value": "USB-A"}).status_code == 409
    assert fact["source_case_id"] == case["id"] and fact["validity"] == "CANDIDATE"
    assert customer.get(base).json()["verified_facts"] == []
    assert customer.get(base + "/fact-review").status_code == 403
    assert [item["id"] for item in staff.get(base + "/fact-review").json()] == [fact["id"]]
    archive_url = f"/api/v1/cases/{case['id']}/devices/{device['id']}/facts/{fact['id']}/archive"
    archive_body = {"expected_case_version": case["version"], "expected_device_revision": 2,
                    "expected_fact_revision": 1}
    assert staff.post(archive_url, json=archive_body).status_code == 409
    decision = {"expected_device_revision": 2, "expected_fact_revision": 1,
                "reason": "现场核对设备端口"}
    verified = staff.post(base + f"/facts/{fact['id']}/verify", json=decision)
    assert verified.status_code == 200, verified.text
    assert verified.json()["verified_by"]
    assert verified.json()["archived_at"] is None
    assert customer.get(base).json()["verified_facts"] == []
    assert staff.post(archive_url, json=archive_body | {
        "expected_device_revision": 3, "expected_fact_revision": 2,
    }).status_code == 409
    started = staff.post(f"/api/v1/cases/{case['id']}/transitions", json={
        "expected_version": case["version"], "target_status": "IN_PROGRESS", "reason": "人工复核处理中",
    })
    assert started.status_code == 200, started.text
    resolved = staff.post(f"/api/v1/cases/{case['id']}/transitions", json={
        "expected_version": started.json()["version"], "target_status": "RESOLVED", "reason": "客户确认原问题已解决",
    })
    assert resolved.status_code == 200, resolved.text
    archive_body = {"expected_case_version": resolved.json()["version"],
                    "expected_device_revision": 3, "expected_fact_revision": 2}
    assert customer.post(archive_url, json=archive_body).status_code == 403
    archived = staff.post(archive_url, json=archive_body)
    assert archived.status_code == 200, archived.text
    assert archived.json()["archived_at"] and archived.json()["archived_by"]
    assert staff.post(archive_url, json=archive_body).json()["id"] == fact["id"]
    visible = customer.get(base).json()["verified_facts"]
    assert len(visible) == 1 and visible[0]["source_case_id"] == case["id"]
    assert visible[0]["verified_by"] and visible[0]["archived_at"]
    assert visible[0]["source"] == "客户陈述" and visible[0]["verified_by"] == "客服核验"
    assert staff.get(base + "/fact-review").json() == []
    retract = staff.post(base + f"/facts/{fact['id']}/retract", json={
        "expected_device_revision": 4, "expected_fact_revision": 3,
        "reason": "后续复核发现端口记录不符",
    })
    assert retract.status_code == 200, retract.text
    assert retract.json()["retraction_reason"] and retract.json()["source_case_id"] == case["id"]
    assert customer.get(base).json()["verified_facts"] == []


def test_fact_cannot_claim_another_case_or_device(app):
    customer = login(app, "customer-a")
    staff = login(app, "staff")
    first = customer.post("/api/v1/devices", json={"model": "A3134"}).json()
    second = customer.post("/api/v1/devices", json={"model": "A1229"}).json()
    case = customer.post("/api/v1/cases", json={"problem_text": "错误设备来源"}).json()
    linked = customer.post(f"/api/v1/cases/{case['id']}/devices", json={
        "device_id": first["id"], "expected_version": 1,
    })
    assert linked.status_code == 200
    body = {"expected_device_revision": 1, "fact_key": "port_type", "value": "USB-C",
            "source_case_id": case["id"]}
    assert staff.post(f"/api/v1/devices/{second['id']}/facts", json=body).status_code == 409
    assert staff.post(f"/api/v1/devices/{first['id']}/facts", json=body | {
        "source_case_id": str(uuid4()),
    }).status_code == 404
