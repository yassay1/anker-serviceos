"""V1 business foundation

Revision ID: 0001_business_foundation
Revises: 
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0001_business_foundation'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Frozen initial schema; later model changes require a new migration.
    op.execute(sa.schema.CreateSchema('serviceos'))
    op.create_table('staff_users',
    sa.Column('display_name', sa.String(length=160), nullable=False),
    sa.Column('external_subject', sa.String(length=240), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_staff_users')),
    sa.UniqueConstraint('external_subject', name=op.f('uq_staff_users_external_subject')),
    schema='serviceos'
    )
    op.create_table('tenants',
    sa.Column('slug', sa.String(length=80), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_tenants')),
    sa.UniqueConstraint('slug', name=op.f('uq_tenants_slug')),
    schema='serviceos'
    )
    op.create_table('customers',
    sa.Column('display_name', sa.String(length=160), nullable=False),
    sa.Column('external_subject', sa.String(length=240), nullable=True),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['serviceos.tenants.id'], name=op.f('fk_customers_tenant_id_tenants')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_customers')),
    sa.UniqueConstraint('tenant_id', 'external_subject', name=op.f('uq_customers_tenant_id_external_subject')),
    sa.UniqueConstraint('tenant_id', 'id', name=op.f('uq_customers_tenant_id_id')),
    schema='serviceos'
    )
    op.create_table('tenant_memberships',
    sa.Column('staff_user_id', sa.UUID(), nullable=False),
    sa.Column('role', sa.String(length=24), server_default='SUPPORT', nullable=False),
    sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("role IN ('SUPPORT','SUPERVISOR','ADMIN')", name=op.f('ck_tenant_memberships_role_values')),
    sa.ForeignKeyConstraint(['staff_user_id'], ['serviceos.staff_users.id'], name=op.f('fk_tenant_memberships_staff_user_id_staff_users')),
    sa.ForeignKeyConstraint(['tenant_id'], ['serviceos.tenants.id'], name=op.f('fk_tenant_memberships_tenant_id_tenants')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_tenant_memberships')),
    sa.UniqueConstraint('tenant_id', 'id', name=op.f('uq_tenant_memberships_tenant_id_id')),
    sa.UniqueConstraint('tenant_id', 'staff_user_id', name=op.f('uq_tenant_memberships_tenant_id_staff_user_id')),
    schema='serviceos'
    )
    op.create_table('conversations',
    sa.Column('customer_id', sa.UUID(), nullable=False),
    sa.Column('channel', sa.String(length=32), server_default='WEB', nullable=False),
    sa.Column('status', sa.String(length=24), server_default='ACTIVE', nullable=False),
    sa.Column('collaboration_mode', sa.String(length=24), server_default='AI_LEAD', nullable=False),
    sa.Column('reply_policy', sa.String(length=24), server_default='AI_AUTO', nullable=False),
    sa.Column('version', sa.Integer(), server_default='1', nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("collaboration_mode <> 'HUMAN_LEAD' OR reply_policy = 'HUMAN_ONLY'", name=op.f('ck_conversations_human_reply_only')),
    sa.CheckConstraint("collaboration_mode IN ('AI_LEAD','CO_SERVICE','HUMAN_LEAD')", name=op.f('ck_conversations_mode_values')),
    sa.CheckConstraint("reply_policy IN ('AI_AUTO','AI_REVIEW_REQUIRED','HUMAN_ONLY')", name=op.f('ck_conversations_policy_values')),
    sa.CheckConstraint("status IN ('ACTIVE','ARCHIVED')", name=op.f('ck_conversations_status_values')),
    sa.CheckConstraint('version >= 1', name=op.f('ck_conversations_version_positive')),
    sa.ForeignKeyConstraint(['tenant_id', 'customer_id'], ['serviceos.customers.tenant_id', 'serviceos.customers.id'], name=op.f('fk_conversations_tenant_id_customers')),
    sa.ForeignKeyConstraint(['tenant_id'], ['serviceos.tenants.id'], name=op.f('fk_conversations_tenant_id_tenants')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_conversations')),
    sa.UniqueConstraint('tenant_id', 'id', name=op.f('uq_conversations_tenant_id_id')),
    schema='serviceos'
    )
    op.create_index('ix_conversations_customer', 'conversations', ['tenant_id', 'customer_id'], unique=False, schema='serviceos')
    op.create_table('device_passports',
    sa.Column('customer_id', sa.UUID(), nullable=False),
    sa.Column('model', sa.String(length=160), nullable=True),
    sa.Column('serial_number', sa.String(length=160), nullable=True),
    sa.Column('identity_status', sa.String(length=24), server_default='UNVERIFIED', nullable=False),
    sa.Column('identity_source', sa.String(length=240), nullable=False),
    sa.Column('verified_by', sa.String(length=160), nullable=True),
    sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revision', sa.Integer(), server_default='1', nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("identity_status <> 'VERIFIED' OR (verified_by IS NOT NULL AND verified_at IS NOT NULL)", name=op.f('ck_device_passports_verified_identity_source')),
    sa.CheckConstraint("identity_status IN ('UNVERIFIED','VERIFIED')", name=op.f('ck_device_passports_identity_values')),
    sa.CheckConstraint('(model IS NOT NULL AND length(trim(model)) > 0) OR (serial_number IS NOT NULL AND length(trim(serial_number)) > 0)', name=op.f('ck_device_passports_identity_material_required')),
    sa.CheckConstraint('revision >= 1', name=op.f('ck_device_passports_revision_positive')),
    sa.ForeignKeyConstraint(['tenant_id', 'customer_id'], ['serviceos.customers.tenant_id', 'serviceos.customers.id'], name=op.f('fk_device_passports_tenant_id_customers')),
    sa.ForeignKeyConstraint(['tenant_id'], ['serviceos.tenants.id'], name=op.f('fk_device_passports_tenant_id_tenants')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_device_passports')),
    sa.UniqueConstraint('tenant_id', 'id', name=op.f('uq_device_passports_tenant_id_id')),
    schema='serviceos'
    )
    op.create_index('ix_devices_customer', 'device_passports', ['tenant_id', 'customer_id'], unique=False, schema='serviceos')
    op.create_table('service_cases',
    sa.Column('customer_id', sa.UUID(), nullable=False),
    sa.Column('problem_text', sa.Text(), nullable=False),
    sa.Column('user_goal', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=24), server_default='OPEN', nullable=False),
    sa.Column('version', sa.Integer(), server_default='1', nullable=False),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('OPEN','IN_PROGRESS','WAITING_CUSTOMER','WAITING_EXTERNAL','RESOLVED','CLOSED')", name=op.f('ck_service_cases_status_values')),
    sa.CheckConstraint('version >= 1', name=op.f('ck_service_cases_version_positive')),
    sa.ForeignKeyConstraint(['tenant_id', 'customer_id'], ['serviceos.customers.tenant_id', 'serviceos.customers.id'], name=op.f('fk_service_cases_tenant_id_customers')),
    sa.ForeignKeyConstraint(['tenant_id'], ['serviceos.tenants.id'], name=op.f('fk_service_cases_tenant_id_tenants')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_service_cases')),
    sa.UniqueConstraint('tenant_id', 'id', name=op.f('uq_service_cases_tenant_id_id')),
    schema='serviceos'
    )
    op.create_index('ix_cases_customer', 'service_cases', ['tenant_id', 'customer_id'], unique=False, schema='serviceos')
    op.create_table('case_conversations',
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('case_id', sa.UUID(), nullable=False),
    sa.Column('conversation_id', sa.UUID(), nullable=False),
    sa.Column('linked_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id', 'case_id'], ['serviceos.service_cases.tenant_id', 'serviceos.service_cases.id'], name=op.f('fk_case_conversations_tenant_id_service_cases')),
    sa.ForeignKeyConstraint(['tenant_id', 'conversation_id'], ['serviceos.conversations.tenant_id', 'serviceos.conversations.id'], name=op.f('fk_case_conversations_tenant_id_conversations')),
    sa.PrimaryKeyConstraint('case_id', 'conversation_id', name=op.f('pk_case_conversations')),
    schema='serviceos'
    )
    op.create_table('case_devices',
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('case_id', sa.UUID(), nullable=False),
    sa.Column('device_id', sa.UUID(), nullable=False),
    sa.Column('role', sa.String(length=32), server_default='AFFECTED', nullable=False),
    sa.Column('is_primary', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('linked_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id', 'case_id'], ['serviceos.service_cases.tenant_id', 'serviceos.service_cases.id'], name=op.f('fk_case_devices_tenant_id_service_cases')),
    sa.ForeignKeyConstraint(['tenant_id', 'device_id'], ['serviceos.device_passports.tenant_id', 'serviceos.device_passports.id'], name=op.f('fk_case_devices_tenant_id_device_passports')),
    sa.PrimaryKeyConstraint('case_id', 'device_id', name=op.f('pk_case_devices')),
    schema='serviceos'
    )
    op.create_index('uq_case_devices_primary', 'case_devices', ['tenant_id', 'case_id'], unique=True, schema='serviceos', postgresql_where=sa.text('is_primary'))
    op.create_table('case_evidence',
    sa.Column('case_id', sa.UUID(), nullable=False),
    sa.Column('source', sa.String(length=240), nullable=False),
    sa.Column('claim_type', sa.String(length=32), nullable=False),
    sa.Column('certainty', sa.String(length=16), server_default='MEDIUM', nullable=False),
    sa.Column('validity', sa.String(length=24), server_default='CANDIDATE', nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('observed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('verified_by', sa.String(length=160), nullable=True),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("certainty IN ('LOW','MEDIUM','HIGH')", name=op.f('ck_case_evidence_certainty_values')),
    sa.CheckConstraint("claim_type <> 'HYPOTHESIS' OR validity <> 'VERIFIED'", name=op.f('ck_case_evidence_hypothesis_not_fact')),
    sa.CheckConstraint("claim_type IN ('USER_STATEMENT','OBSERVATION','TOOL_RESULT','HYPOTHESIS')", name=op.f('ck_case_evidence_claim_values')),
    sa.CheckConstraint("validity <> 'VERIFIED' OR (verified_at IS NOT NULL AND verified_by IS NOT NULL)", name=op.f('ck_case_evidence_verification_source')),
    sa.CheckConstraint("validity IN ('CANDIDATE','VERIFIED','RETRACTED')", name=op.f('ck_case_evidence_validity_values')),
    sa.ForeignKeyConstraint(['tenant_id', 'case_id'], ['serviceos.service_cases.tenant_id', 'serviceos.service_cases.id'], name=op.f('fk_case_evidence_tenant_id_service_cases')),
    sa.ForeignKeyConstraint(['tenant_id'], ['serviceos.tenants.id'], name=op.f('fk_case_evidence_tenant_id_tenants')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_case_evidence')),
    sa.UniqueConstraint('tenant_id', 'id', name=op.f('uq_case_evidence_tenant_id_id')),
    schema='serviceos'
    )
    op.create_table('device_facts',
    sa.Column('device_id', sa.UUID(), nullable=False),
    sa.Column('source_case_id', sa.UUID(), nullable=True),
    sa.Column('fact_key', sa.String(length=120), nullable=False),
    sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('source_kind', sa.String(length=24), nullable=False),
    sa.Column('source', sa.String(length=240), nullable=False),
    sa.Column('validity', sa.String(length=24), server_default='CANDIDATE', nullable=False),
    sa.Column('verifier_kind', sa.String(length=24), nullable=True),
    sa.Column('verified_by', sa.String(length=160), nullable=True),
    sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('retracted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('retraction_reason', sa.Text(), nullable=True),
    sa.Column('revision', sa.Integer(), server_default='1', nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("source_kind IN ('USER','MODEL','TOOL','HUMAN')", name=op.f('ck_device_facts_source_values')),
    sa.CheckConstraint("validity <> 'RETRACTED' OR (retracted_at IS NOT NULL AND retraction_reason IS NOT NULL)", name=op.f('ck_device_facts_retraction_source')),
    sa.CheckConstraint("validity <> 'VERIFIED' OR (verified_by IS NOT NULL AND verified_at IS NOT NULL AND verifier_kind IS NOT NULL AND verifier_kind IN ('HUMAN','TRUSTED_TOOL'))", name=op.f('ck_device_facts_verification_source')),
    sa.CheckConstraint("validity IN ('CANDIDATE','VERIFIED','RETRACTED')", name=op.f('ck_device_facts_validity_values')),
    sa.CheckConstraint('revision >= 1', name=op.f('ck_device_facts_revision_positive')),
    sa.ForeignKeyConstraint(['tenant_id', 'device_id'], ['serviceos.device_passports.tenant_id', 'serviceos.device_passports.id'], name=op.f('fk_device_facts_tenant_id_device_passports')),
    sa.ForeignKeyConstraint(['tenant_id', 'source_case_id'], ['serviceos.service_cases.tenant_id', 'serviceos.service_cases.id'], name=op.f('fk_device_facts_tenant_id_service_cases')),
    sa.ForeignKeyConstraint(['tenant_id'], ['serviceos.tenants.id'], name=op.f('fk_device_facts_tenant_id_tenants')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_device_facts')),
    sa.UniqueConstraint('tenant_id', 'id', name=op.f('uq_device_facts_tenant_id_id')),
    schema='serviceos'
    )
    op.create_index('ix_device_facts_device', 'device_facts', ['tenant_id', 'device_id'], unique=False, schema='serviceos')
    op.create_table('messages',
    sa.Column('conversation_id', sa.UUID(), nullable=False),
    sa.Column('author_kind', sa.String(length=24), nullable=False),
    sa.Column('author_customer_id', sa.UUID(), nullable=True),
    sa.Column('author_staff_id', sa.UUID(), nullable=True),
    sa.Column('visibility', sa.String(length=16), server_default='PUBLIC', nullable=False),
    sa.Column('content', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('related_case_id', sa.UUID(), nullable=True),
    sa.Column('client_message_id', sa.UUID(), nullable=True),
    sa.Column('request_hash', sa.String(length=64), nullable=True),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(author_kind = 'CUSTOMER' AND author_customer_id IS NOT NULL AND author_staff_id IS NULL AND visibility = 'PUBLIC') OR (author_kind = 'STAFF' AND author_staff_id IS NOT NULL AND author_customer_id IS NULL) OR (author_kind IN ('AGENT','SYSTEM') AND author_customer_id IS NULL AND author_staff_id IS NULL)", name=op.f('ck_messages_author_identity')),
    sa.CheckConstraint("jsonb_typeof(content) = 'array' AND jsonb_array_length(content) > 0", name=op.f('ck_messages_content_array')),
    sa.CheckConstraint("visibility IN ('PUBLIC','INTERNAL')", name=op.f('ck_messages_visibility_values')),
    sa.CheckConstraint('client_message_id IS NULL OR request_hash IS NOT NULL', name=op.f('ck_messages_idempotency_hash')),
    sa.ForeignKeyConstraint(['tenant_id', 'author_customer_id'], ['serviceos.customers.tenant_id', 'serviceos.customers.id'], name=op.f('fk_messages_tenant_id_customers')),
    sa.ForeignKeyConstraint(['tenant_id', 'author_staff_id'], ['serviceos.tenant_memberships.tenant_id', 'serviceos.tenant_memberships.staff_user_id'], name=op.f('fk_messages_tenant_id_tenant_memberships')),
    sa.ForeignKeyConstraint(['tenant_id', 'conversation_id'], ['serviceos.conversations.tenant_id', 'serviceos.conversations.id'], name=op.f('fk_messages_tenant_id_conversations')),
    sa.ForeignKeyConstraint(['tenant_id', 'related_case_id'], ['serviceos.service_cases.tenant_id', 'serviceos.service_cases.id'], name=op.f('fk_messages_tenant_id_service_cases')),
    sa.ForeignKeyConstraint(['tenant_id'], ['serviceos.tenants.id'], name=op.f('fk_messages_tenant_id_tenants')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_messages')),
    sa.UniqueConstraint('tenant_id', 'conversation_id', 'client_message_id', name=op.f('uq_messages_tenant_id_conversation_id_client_message_id')),
    sa.UniqueConstraint('tenant_id', 'id', name=op.f('uq_messages_tenant_id_id')),
    schema='serviceos'
    )
    op.create_index('ix_messages_conversation', 'messages', ['tenant_id', 'conversation_id', 'created_at', 'id'], unique=False, schema='serviceos')
    # ### end Alembic commands ###


def downgrade() -> None:
    # Removes only this migration's business objects; never uses CASCADE.
    op.drop_index('ix_messages_conversation', table_name='messages', schema='serviceos')
    op.drop_table('messages', schema='serviceos')
    op.drop_index('ix_device_facts_device', table_name='device_facts', schema='serviceos')
    op.drop_table('device_facts', schema='serviceos')
    op.drop_table('case_evidence', schema='serviceos')
    op.drop_index('uq_case_devices_primary', table_name='case_devices', schema='serviceos', postgresql_where=sa.text('is_primary'))
    op.drop_table('case_devices', schema='serviceos')
    op.drop_table('case_conversations', schema='serviceos')
    op.drop_index('ix_cases_customer', table_name='service_cases', schema='serviceos')
    op.drop_table('service_cases', schema='serviceos')
    op.drop_index('ix_devices_customer', table_name='device_passports', schema='serviceos')
    op.drop_table('device_passports', schema='serviceos')
    op.drop_index('ix_conversations_customer', table_name='conversations', schema='serviceos')
    op.drop_table('conversations', schema='serviceos')
    op.drop_table('tenant_memberships', schema='serviceos')
    op.drop_table('customers', schema='serviceos')
    op.drop_table('tenants', schema='serviceos')
    op.drop_table('staff_users', schema='serviceos')
    op.execute(sa.schema.DropSchema('serviceos'))
    # ### end Alembic commands ###
