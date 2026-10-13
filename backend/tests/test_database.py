from datetime import datetime, timezone
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from conftest import migration_config
from serviceos_api.persistence.database import build_engine
from serviceos_api.persistence.models import (
    BUSINESS_SCHEMA, Base, CaseConversation, CaseDevice, CaseEvidence, Conversation,
    Customer, DeviceFact, DevicePassport, Message, ServiceCase, StaffUser, Tenant, TenantMembership,
)


def seed_owner(session):
    tenant = Tenant(slug=f"test-{uuid4().hex}", name="Test tenant")
    session.add(tenant)
    session.flush()
    customer = Customer(tenant_id=tenant.id, display_name="Test customer")
    session.add(customer)
    session.flush()
    return tenant, customer


def seed_case_and_conversation(session, tenant, customer):
    case = ServiceCase(tenant_id=tenant.id, customer_id=customer.id, problem_text="充电异常")
    conversation = Conversation(tenant_id=tenant.id, customer_id=customer.id)
    session.add_all([case, conversation])
    session.flush()
    return case, conversation


def device(tenant, customer, **kwargs):
    return DevicePassport(tenant_id=tenant.id, customer_id=customer.id,
                          model="A1229", identity_source="user_statement", **kwargs)


def reject(session, record, sqlstate):
    with pytest.raises(IntegrityError) as caught:
        with session.begin_nested():
            session.add(record)
            session.flush()
    assert caught.value.orig.sqlstate == sqlstate


def test_no_implicit_sqlite_database():
    with pytest.raises(ValueError, match="postgresql"):
        build_engine("sqlite:///:memory:")


def test_real_postgres_migration_round_trip(database_engine):
    assert database_engine.dialect.name == "postgresql"
    config = migration_config(database_engine)
    expected = {table.name for table in Base.metadata.sorted_tables}
    assert set(inspect(database_engine).get_table_names(schema=BUSINESS_SCHEMA)) == expected
    command.downgrade(config, "base")
    assert BUSINESS_SCHEMA not in inspect(database_engine).get_schema_names()
    command.upgrade(config, "head")
    assert set(inspect(database_engine).get_table_names(schema=BUSINESS_SCHEMA)) == expected
    command.check(config)


def test_case_is_persisted_without_a_device(db_session):
    tenant, customer = seed_owner(db_session)
    case, _ = seed_case_and_conversation(db_session, tenant, customer)
    assert case.status == "OPEN" and case.version == 1
    assert db_session.scalar(select(func.count()).select_from(CaseDevice).where(CaseDevice.case_id == case.id)) == 0
    assert "device_id" not in ServiceCase.__table__.columns


def test_case_device_and_conversation_links_are_many_to_many(db_session):
    tenant, customer = seed_owner(db_session)
    case1, conv1 = seed_case_and_conversation(db_session, tenant, customer)
    case2, conv2 = seed_case_and_conversation(db_session, tenant, customer)
    dev1, dev2 = device(tenant, customer), device(tenant, customer)
    db_session.add_all([dev1, dev2])
    db_session.flush()
    db_session.add_all([
        CaseDevice(tenant_id=tenant.id, case_id=case1.id, device_id=dev1.id, is_primary=True),
        CaseDevice(tenant_id=tenant.id, case_id=case1.id, device_id=dev2.id),
        CaseDevice(tenant_id=tenant.id, case_id=case2.id, device_id=dev1.id),
        CaseConversation(tenant_id=tenant.id, case_id=case1.id, conversation_id=conv1.id),
        CaseConversation(tenant_id=tenant.id, case_id=case1.id, conversation_id=conv2.id),
        CaseConversation(tenant_id=tenant.id, case_id=case2.id, conversation_id=conv1.id),
    ])
    db_session.flush()
    for model, field, value in [(CaseDevice, CaseDevice.case_id, case1.id), (CaseDevice, CaseDevice.device_id, dev1.id),
                                (CaseConversation, CaseConversation.case_id, case1.id),
                                (CaseConversation, CaseConversation.conversation_id, conv1.id)]:
        assert db_session.scalar(select(func.count()).select_from(model).where(field == value)) == 2


@pytest.mark.parametrize("association", ["device", "conversation", "fact", "message", "customer"])
def test_cross_tenant_foreign_keys_are_rejected(db_session, association):
    tenant1, customer1 = seed_owner(db_session)
    tenant2, customer2 = seed_owner(db_session)
    case1, _ = seed_case_and_conversation(db_session, tenant1, customer1)
    case2, conv2 = seed_case_and_conversation(db_session, tenant2, customer2)
    dev2 = device(tenant2, customer2)
    db_session.add(dev2)
    db_session.flush()
    records = {
        "device": CaseDevice(tenant_id=tenant1.id, case_id=case1.id, device_id=dev2.id),
        "conversation": CaseConversation(tenant_id=tenant1.id, case_id=case1.id, conversation_id=conv2.id),
        "fact": DeviceFact(tenant_id=tenant2.id, device_id=dev2.id, source_case_id=case1.id,
                           fact_key="symptom", value="no charge", source="user", source_kind="USER"),
        "message": Message(tenant_id=tenant1.id, conversation_id=conv2.id, author_kind="CUSTOMER",
                           author_customer_id=customer1.id, content=[{"type": "text", "text": "hello"}]),
        "customer": ServiceCase(tenant_id=tenant1.id, customer_id=customer2.id, problem_text="invalid owner"),
    }
    reject(db_session, records[association], "23503")


def test_only_one_primary_device_per_case(db_session):
    tenant, customer = seed_owner(db_session)
    case, _ = seed_case_and_conversation(db_session, tenant, customer)
    dev1, dev2 = device(tenant, customer), device(tenant, customer)
    db_session.add_all([dev1, dev2])
    db_session.flush()
    db_session.add(CaseDevice(tenant_id=tenant.id, case_id=case.id, device_id=dev1.id, is_primary=True))
    db_session.flush()
    reject(db_session, CaseDevice(tenant_id=tenant.id, case_id=case.id, device_id=dev2.id, is_primary=True), "23505")


def test_message_idempotency_key_is_scoped_to_conversation(db_session):
    tenant, customer = seed_owner(db_session)
    _, conv1 = seed_case_and_conversation(db_session, tenant, customer)
    _, conv2 = seed_case_and_conversation(db_session, tenant, customer)
    key = uuid4()

    def message(conversation_id):
        return Message(tenant_id=tenant.id, conversation_id=conversation_id, author_kind="CUSTOMER",
                       author_customer_id=customer.id, client_message_id=key, request_hash="a" * 64,
                       content=[{"type": "text", "text": "hello"}])

    db_session.add_all([message(conv1.id), message(conv2.id)])
    db_session.flush()
    reject(db_session, message(conv1.id), "23505")
    # API-level same-payload replay and conflicting-payload 409 are D104 work.


def test_customer_cannot_write_an_internal_note(db_session):
    tenant, customer = seed_owner(db_session)
    _, conversation = seed_case_and_conversation(db_session, tenant, customer)
    reject(db_session, Message(tenant_id=tenant.id, conversation_id=conversation.id,
                              author_kind="CUSTOMER", author_customer_id=customer.id,
                              visibility="INTERNAL", content=[{"type": "text", "text": "private"}]), "23514")


def test_staff_author_must_belong_to_conversation_tenant(db_session):
    tenant1, customer1 = seed_owner(db_session)
    tenant2, _ = seed_owner(db_session)
    _, conversation = seed_case_and_conversation(db_session, tenant1, customer1)
    staff = StaffUser(display_name="Support")
    db_session.add(staff)
    db_session.flush()
    db_session.add(TenantMembership(tenant_id=tenant2.id, staff_user_id=staff.id))
    db_session.flush()
    reject(db_session, Message(tenant_id=tenant1.id, conversation_id=conversation.id,
                              author_kind="STAFF", author_staff_id=staff.id,
                              content=[{"type": "text", "text": "hello"}]), "23503")


@pytest.mark.parametrize("missing", ["verified_by", "verified_at", "verifier_kind"])
def test_device_fact_requires_verification_provenance(db_session, missing):
    tenant, customer = seed_owner(db_session)
    dev = device(tenant, customer)
    db_session.add(dev)
    db_session.flush()
    record = DeviceFact(tenant_id=tenant.id, device_id=dev.id, fact_key="port",
                        value="USB-A", source="candidate", source_kind="MODEL", validity="VERIFIED",
                        verified_by="staff:test", verified_at=datetime.now(timezone.utc), verifier_kind="HUMAN")
    setattr(record, missing, None)
    reject(db_session, record, "23514")


def test_fact_candidate_and_retraction_remain_distinct(db_session):
    tenant, customer = seed_owner(db_session)
    dev = device(tenant, customer)
    db_session.add(dev)
    db_session.flush()
    fact = DeviceFact(tenant_id=tenant.id, device_id=dev.id, fact_key="symptom",
                      value="no charge", source_kind="MODEL", source="run:test")
    db_session.add(fact)
    db_session.flush()
    assert fact.validity == "CANDIDATE" and fact.verified_at is None
    fact.validity = "RETRACTED"
    fact.retracted_at = datetime.now(timezone.utc)
    fact.retraction_reason = "New evidence contradicted the candidate"
    fact.revision = 2
    db_session.flush()
    assert fact.source == "run:test" and fact.retraction_reason


def test_unknown_identity_is_not_materialized_as_a_fake_device(db_session):
    tenant, customer = seed_owner(db_session)
    reject(db_session, DevicePassport(tenant_id=tenant.id, customer_id=customer.id,
                                     identity_source="unknown"), "23514")


def test_hypothesis_is_not_verified_evidence(db_session):
    tenant, customer = seed_owner(db_session)
    case, _ = seed_case_and_conversation(db_session, tenant, customer)
    reject(db_session, CaseEvidence(tenant_id=tenant.id, case_id=case.id, source="model",
                                   claim_type="HYPOTHESIS", summary="guess", validity="VERIFIED",
                                   verified_by="model", verified_at=datetime.now(timezone.utc)), "23514")


def test_human_lead_cannot_use_ai_auto_reply_policy(db_session):
    tenant, customer = seed_owner(db_session)
    reject(db_session, Conversation(tenant_id=tenant.id, customer_id=customer.id,
                                    collaboration_mode="HUMAN_LEAD", reply_policy="AI_AUTO"), "23514")


def test_committed_data_survives_a_new_database_connection(database_engine):
    with Session(database_engine) as session:
        tenant, customer = seed_owner(session)
        case, conversation = seed_case_and_conversation(session, tenant, customer)
        case_id, conv_id = case.id, conversation.id
        session.add(Message(tenant_id=tenant.id, conversation_id=conversation.id,
                            author_kind="CUSTOMER", author_customer_id=customer.id,
                            content=[{"type": "text", "text": "persistent message"}]))
        session.commit()
    database_engine.dispose()
    with Session(database_engine) as restored:
        assert restored.get(ServiceCase, case_id).problem_text == "充电异常"
        message = restored.scalar(select(Message).where(Message.conversation_id == conv_id))
        assert message.content[0]["text"] == "persistent message"
        assert message.created_at.tzinfo is not None
