"""Deterministic conversation labels derived from authorized public messages."""

import re

from sqlalchemy import select

from serviceos_api.application.contracts import ConversationRead
from serviceos_api.persistence.models import Message


def conversation_title(text: str) -> str:
    if not text.strip():
        return '新会话'
    text = re.sub(r'https?://\S+|[\w.+-]+@[\w.-]+\.[a-zA-Z]+|(?<!\d)\d{7,}(?!\d)', '', text[:2000])
    text = re.sub(r'[\x00-\x1f\x7f]+', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip(' #>*_`，,。.!！?？:：')
    for _ in range(4):
        text = re.sub(r'^(?:你好|您好|请问|麻烦帮我|请帮我|我想咨询一下|我想咨询|我的)[，,！!\s]*', '', text)
    text = re.split(r'[。！？!?]', text, maxsplit=1)[0]
    text = re.sub(r'[，,\s]*(?:该怎么排查|该怎么办|这是怎么回事|怎么解决|怎么办|帮我看看)$', '', text)
    text = text.strip(' ，,。.!！?？:：')
    if not text:
        return '售后咨询'
    return text if len(text) <= 24 else text[:23] + '…'


def conversation_reads(session, tenant_id, records) -> list[ConversationRead]:
    records = list(records)
    if not records:
        return []
    # One bounded batch lookup, including existing conversations; internal notes,
    # staff replies, and other tenants can never supply a customer-visible title.
    first_messages = session.scalars(select(Message).where(
        Message.tenant_id == tenant_id,
        Message.conversation_id.in_([row.id for row in records]),
        Message.author_kind == 'CUSTOMER', Message.visibility == 'PUBLIC',
    ).distinct(Message.conversation_id).order_by(
        Message.conversation_id, Message.created_at, Message.id,
    )).all()
    titles = {row.conversation_id: conversation_title(' '.join(
        part.get('text', '') for part in row.content if part.get('type') == 'text'
    )) for row in first_messages}
    return [ConversationRead.model_validate(row).model_copy(update={'title': titles.get(row.id, '新会话')})
            for row in records]
