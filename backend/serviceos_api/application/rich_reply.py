"""Inert rich content on the existing text message; business actions remain elsewhere."""
import re
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select


class ContentModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


ShortText = Annotated[str, Field(min_length=1, max_length=500)]


class ReplyStep(ContentModel):
    title: Annotated[str, Field(min_length=1, max_length=100)]
    description: ShortText


class ImageFocus(ContentModel):
    x: float = Field(ge=0, le=1, allow_inf_nan=False)
    y: float = Field(ge=0, le=1, allow_inf_nan=False)
    width: float = Field(gt=0, le=1, allow_inf_nan=False)
    height: float = Field(gt=0, le=1, allow_inf_nan=False)

    @model_validator(mode='after')
    def inside_image(self):
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError('focus_outside_image')
        return self


class ReplyEvent(ContentModel):
    label: ShortText
    time: str = Field(max_length=64)
    description: ShortText
    state: Literal['recorded', 'pending', 'current', 'completed', 'failed'] = 'recorded'


class ReplyBlock(ContentModel):
    type: Literal['summary', 'steps', 'table', 'image', 'image_focus', 'alert', 'timeline', 'status', 'reference', 'actions']
    title: str = Field(default='', max_length=120)
    text: str = Field(default='', max_length=2000)
    items: list[ReplyStep] = Field(default_factory=list, max_length=6)
    columns: list[ShortText] = Field(default_factory=list, max_length=5)
    rows: list[list[ShortText]] = Field(default_factory=list, max_length=8)
    case_id: str | None = None
    evidence_id: str | None = None
    focus: ImageFocus | None = None
    source_id: str | None = Field(default=None, max_length=100)
    source_url: str | None = Field(default=None, max_length=500)
    severity: Literal['info', 'warning', 'danger'] = 'info'
    entries: list[ReplyEvent] = Field(default_factory=list, max_length=8)
    status_code: str | None = Field(default=None, max_length=40)
    action: Literal['upload_evidence', 'request_assistance', 'view_case'] | None = None

    @field_validator('case_id', 'evidence_id')
    @classmethod
    def identifier(cls, value):
        if value is not None and str(UUID(value)) != value.lower():
            raise ValueError('invalid_resource_id')
        return value

    @model_validator(mode='after')
    def valid_shape(self):
        if self.type == 'steps' and not self.items:
            raise ValueError('steps_empty')
        if self.type == 'table' and (len(self.columns) < 2 or not self.rows or
                                     any(len(row) != len(self.columns) for row in self.rows)):
            raise ValueError('table_shape_invalid')
        if self.type in ('image', 'image_focus') and (not self.evidence_id or not self.case_id):
            raise ValueError('image_reference_required')
        if self.type == 'reference' and not self.source_id:
            raise ValueError('source_required')
        if self.type == 'actions' and not self.action:
            raise ValueError('action_required')
        if self.type != 'steps' and self.items or self.type != 'table' and (self.columns or self.rows):
            raise ValueError('unexpected_block_payload')
        if self.type != 'timeline' and self.entries or self.type != 'image_focus' and self.focus is not None:
            raise ValueError('unexpected_block_payload')
        return self


class QuickReply(ContentModel):
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,40}$')
    label: str = Field(min_length=2, max_length=40)
    message: str = Field(min_length=2, max_length=500)


class RichReply(ContentModel):
    schema_version: Literal[1] = 1
    blocks: list[ReplyBlock] = Field(default_factory=list, max_length=8)
    quick_replies: list[QuickReply] = Field(default_factory=list, max_length=4)

    @model_validator(mode='after')
    def bounded_and_unique(self):
        if self.quick_replies and len(self.quick_replies) < 2:
            raise ValueError('quick_replies_need_two_options')
        for name in ('id', 'label', 'message'):
            values = [getattr(item, name).strip().casefold() for item in self.quick_replies]
            if len(values) != len(set(values)):
                raise ValueError('quick_replies_duplicate')
        if len(self.model_dump_json()) > 18000:
            raise ValueError('rich_reply_too_large')
        return self


# Layout guidance, not fabricated answers. Knowledge/tool results fill the actual content.
SCENARIO_GUIDANCE = {
    'charging': ('充电', '断连', '线材', '接口'),
    'power': ('开机', '指示灯', '电量'),
    'evidence': ('图片', '照片', '补拍', '外观'),
    'progress': ('工单', '进度', '售后申请', '物流', '保修'),
}


def reply_guidance(text: str) -> str:
    scenarios = [name for name, words in SCENARIO_GUIDANCE.items() if any(word in text for word in words)]
    return ('\n富内容场景提示：' + ', '.join(scenarios) + '。' if scenarios else '') + '''
沿用同一个 Agent 的工具和上下文，在最终 JSON 的 text 之外可选加入 rich。
rich 格式：{"schema_version":1,"blocks":[],"quick_replies":[]}。简单问答只给 text。
普通故障选 1 个 steps 块，确有分支对比时增加 table；先 lookup_manual，不套用其他型号的接口、功率或政策。
blocks 的 type 仅有 summary/steps/table/image/image_focus/alert/timeline/status/reference/actions。
每块可选 title/text。steps: items=[{"title":"标题","description":"说明"}]，最多6步。
table: columns=["观察结果","可能方向","下一步"],rows=[["…","…","…"]]，最多5列8行；推测必须明确为待确认。
alert: severity=info/warning/danger。鼓包、冒烟、漏液、异味或明显过热时优先停止使用/充电和现有人工协助，不拆机、不继续测试。
status/timeline: 只给从 get_service_progress 或上下文获得的 case_id，标题和真实状态/事件由服务器生成；不自行写 entries/status_code。
image: 只给 image_evidence 中的 case_id/evidence_id。只有 VISION_INPUT 中的图片才真正可见，否则不得声称已查看图片或诊断外观。
image_focus 可带 focus={x,y,width,height} 的0到1坐标；当前无人工核验定位链路，服务器会降级为原图，不能声称已经可靠裁切。
reference: source_id 必须是本轮 lookup_manual 返回的 SOURCE 文件名；不提供 URL，服务器补可信链接。
actions: action 只可选 upload_evidence/request_assistance/view_case；这是打开已有页面/协助入口，不代表执行售后。
保修/退换货/物流仅根据真实查询和可信资料，查不到就说明；绝不从赛题静态订单推断实时状态。
如果适合继续服务，同次输出 2到4 条 quick_replies，优先3条，每项为 {"id":"短slug","label":"8到18字简短问题","message":"点击后客户实际发送的完整问题"}。
quick_replies 是客户的新问题，不是答案选项或执行动作；不要与 ui_proposal.options 重复，不重复历史已回答/已展示的追问，也不编造已做过的操作。
已解决、结束或人工主导时可不生成 quick_replies。绝不为了卡片重复输出整段 text；text 是简短自然结论及文本降级摘要。
所有富内容是建议/展示，不改变工单状态、可信设备事实、审批或人工接续规则。不得输出 HTML/CSS/JS、远程图片地址或本地文件路径。
'''


STATUS_LABELS = {'OPEN': '已建立', 'IN_PROGRESS': '处理中', 'WAITING_CUSTOMER': '等待客户补充',
                 'WAITING_EXTERNAL': '等待外部处理', 'RESOLVED': '已核验解决', 'CLOSED': '已关闭'}

RISK = re.compile(r'(?<!没有)(?<!无)(?<!不)(鼓包|冒烟|漏液|烧焦|烫手|异味|异常发热|明显过热|过热)')


def _safety_reply(reply: RichReply) -> RichReply:
    """Keep only content that is replaced with server-owned facts or neutral copy."""
    safe_types = {'image', 'image_focus', 'status', 'timeline', 'reference', 'actions'}
    blocks = []
    for item in reply.blocks:
        if item.type not in safe_types:
            continue
        if item.type in ('image', 'image_focus'):
            blocks.append(item.model_copy(update={
                'type': 'image', 'title': '用户提供的图片',
                'text': '已收到设备图片；无法据此确认故障原因。请先遵循安全提示。',
                'focus': None,
            }))
        else:
            blocks.append(item)
    return reply.model_copy(update={'blocks': blocks, 'quick_replies': []})
SAFETY_TEXT = '如果设备出现鼓包、冒烟、漏液、异味或明显过热，请停止使用和充电，保持安全距离，不要拆机、挤压或继续通电排查，并通过现有入口联系人工客服。单凭描述不能确认故障原因。'


def project_reply(session, conversation, run, draft, related_case_id=None):
    """Bind model display requests to current authorized records at publication time."""
    from serviceos_api.persistence.models import (CaseAction, CaseConversation, CaseImageEvidence,
        CaseVerification, Message, ServiceCase, ServiceTask)

    try:
        reply = RichReply.model_validate(draft)
    except (ValueError, TypeError):
        return None
    cases = session.scalars(select(ServiceCase).join(CaseConversation, CaseConversation.case_id == ServiceCase.id).where(
        CaseConversation.conversation_id == conversation.id, ServiceCase.tenant_id == conversation.tenant_id,
        ServiceCase.customer_id == conversation.customer_id, ServiceCase.archived_at.is_(None))).all()
    by_id = {str(case.id): case for case in cases}
    payload = run.result_payload or {}
    retrieved = {item['source_id']: item for item in payload.get('retrieved_sources', []) if isinstance(item, dict) and 'source_id' in item}
    vision = set(payload.get('vision_evidence_ids', []))
    projected = []
    source_message = session.scalar(select(Message).where(Message.id == run.message_id,
        Message.tenant_id == conversation.tenant_id, Message.conversation_id == conversation.id))
    safety = bool(source_message and RISK.search(' '.join(part.get('text', '') for part in source_message.content)))
    if safety:
        reply = _safety_reply(reply)
    for item in reply.blocks:
        block = item.model_dump(mode='json')
        case_id = item.case_id or (str(related_case_id) if related_case_id else next(iter(by_id), None) if len(by_id) == 1 else None)
        case = by_id.get(case_id)
        # Model-authored resource URLs, completion claims and events are never trusted.
        block['source_url'] = None
        block['entries'] = []
        block['status_code'] = None
        if item.type in ('status', 'timeline'):
            if case is None:
                continue
            block.update(case_id=str(case.id), text=STATUS_LABELS.get(case.status, case.status), status_code=case.status)
            block['title'] = '服务处理记录' if item.type == 'timeline' else '当前服务状态'
            if item.type == 'timeline':
                entries = [{'label': '服务案例建立', 'time': case.created_at.isoformat(), 'description': '问题记录已保存。', 'state': 'completed'}]
                for model, label in ((ServiceTask, '人工协作任务建立'), (CaseAction, '模拟售后动作记录'), (CaseVerification, '客户结果核验')):
                    rows = session.scalars(select(model).where(model.case_id == case.id, model.tenant_id == conversation.tenant_id)
                                           .order_by(model.created_at.desc()).limit(3)).all()
                    for row in rows:
                        current = getattr(row, 'status', None) or getattr(row, 'decision', '')
                        label_map = {'OPEN': '等待处理', 'ASSIGNED': '人工处理中', 'CLOSED': '任务已关闭',
                            'WAITING_APPROVAL': '等待审批', 'APPROVED': '已批准，等待执行', 'EXECUTING': '正在执行',
                            'SUCCEEDED': '已取得成功模拟回执', 'FAILED': '执行未成功', 'REJECTED': '申请被拒绝',
                            'UNKNOWN': '结果未知，等待对账', 'VERIFIED_RESOLVED': '客户已确认解决',
                            'NOT_RESOLVED': '客户反馈未解决', 'PENDING': '等待核验'}
                        state = ('completed' if current in ('CLOSED', 'SUCCEEDED', 'VERIFIED_RESOLVED') else
                                 'failed' if current in ('FAILED', 'REJECTED', 'NOT_RESOLVED') else
                                 'current' if current in ('ASSIGNED', 'APPROVED', 'EXECUTING') else 'pending')
                        entries.append({'label': label, 'time': row.created_at.isoformat(),
                                        'description': label_map.get(current, '状态待确认'), 'state': state})
                block['entries'] = sorted(entries, key=lambda entry: entry['time'])[-8:]
        elif item.type in ('image', 'image_focus'):
            if case is None:
                continue
            image = session.scalar(select(CaseImageEvidence).where(
                CaseImageEvidence.id == UUID(item.evidence_id), CaseImageEvidence.case_id == case.id,
                CaseImageEvidence.tenant_id == conversation.tenant_id, CaseImageEvidence.visibility == 'PUBLIC',
                CaseImageEvidence.inspection_status == 'CLEAN', CaseImageEvidence.verification != 'RETRACTED'))
            if image is None:
                continue
            # No trustworthy ROI-verification source exists yet. Show the actual original.
            block.update(type='image', focus=None, case_id=str(case.id), title='用户提供的图片')
            if str(image.id) not in vision:
                block['text'] = '此处展示上传原图；本轮未启用图像理解，不能据此确认故障。可补拍正对关键部位、光线充足的近景。'
            else:
                block['text'] = (item.text[:1500] + '\n图片仅支持外观观察，不能确认内部故障；尚无可靠定位依据，保留原图。').strip()
        elif item.type == 'reference':
            source = retrieved.get(item.source_id)
            if source is None:
                continue
            block.update(title=source.get('title', item.source_id), text='本轮检索来源 · ' + source.get('version', ''),
                         source_url=source.get('url'))
        elif item.type == 'actions':
            if item.action in ('upload_evidence', 'view_case') and case is None:
                continue
            block['case_id'] = str(case.id) if case else None
            block['title'] = {'upload_evidence': '补充图片证据', 'view_case': '查看服务案例',
                              'request_assistance': '打开人工协助入口'}[item.action]
            block['text'] = '将打开已有服务入口；不会直接批准或执行售后操作。'
        projected.append(block)
    if safety:
        projected = [{'type': 'alert', 'title': '先确认安全', 'text': SAFETY_TEXT, 'severity': 'danger'},
                     {'type': 'actions', 'title': '打开人工协助入口', 'action': 'request_assistance',
                      'text': '打开现有协助入口，由你确认后再提交。'},
                     *[item for item in projected if item['type'] not in ('alert', 'actions')]][:8]
    quick = reply.quick_replies
    previous = session.scalars(select(Message).where(Message.conversation_id == conversation.id,
        Message.tenant_id == conversation.tenant_id, Message.visibility == 'PUBLIC')
        .order_by(Message.created_at.desc(), Message.id.desc()).limit(12)).all()
    used = set()
    for message in previous:
        for part in message.content:
            if message.author_kind == 'CUSTOMER':
                used.add(part.get('text', '').strip().casefold())
            previous_rich = part.get('rich')
            for option in previous_rich.get('quick_replies', []) if isinstance(previous_rich, dict) else []:
                if isinstance(option, dict):
                    used.update((option.get('label', '').strip().casefold(), option.get('message', '').strip().casefold()))
    quick = [item for item in quick if item.label.strip().casefold() not in used and item.message.strip().casefold() not in used]
    if safety or conversation.collaboration_mode != 'AI_LEAD' or conversation.reply_policy != 'AI_AUTO' or (
        cases and all(case.status in ('RESOLVED', 'CLOSED') for case in cases)):
        quick = []
    if len(quick) < 2:
        quick = []
    try:
        return RichReply.model_validate({'schema_version': 1, 'blocks': projected,
            'quick_replies': [item.model_dump() for item in quick]}).model_dump(mode='json')
    except (ValueError, TypeError):
        return None
