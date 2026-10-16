"""Optional vision input, reusing the authorized evidence storage and the same Agent."""
import base64
import os
from uuid import UUID


def image_input(service, settings, context, text):
    if os.getenv('SERVICEOS_LLM_VISION') != '1' or not any(word in text for word in ('图', '照片', '接口', '外观', '标签', '指示灯')):
        return []
    from serviceos_api.application.auth import Principal
    from serviceos_api.application.evidence import EvidenceService
    from serviceos_api.application.errors import ServiceError
    from serviceos_api.application.evidence_storage import EvidenceStorageFailure
    from serviceos_api.integrations.local_evidence_storage import evidence_storage_from_settings

    candidates = sorted((row for row in context.get('image_evidence', [])
                         if row.get('inspection_status') == 'CLEAN' and row.get('verification') != 'RETRACTED'),
                        key=lambda row: row.get('created_at', ''), reverse=True)
    if not candidates:
        return []
    run, _, conversation, _ = service._active_execution()
    candidate = candidates[0]
    try:
        actor = Principal(conversation.tenant_id, conversation.customer_id, 'CUSTOMER', '当前客户')
        evidence = EvidenceService(service.session, actor, evidence_storage_from_settings(settings))
        raw, media_type = evidence.read_content(UUID(candidate['case_id']), UUID(candidate['evidence_id']))
        if len(raw) > 2 * 1024 * 1024 or media_type not in ('image/jpeg', 'image/png', 'image/webp'):
            return []
    except (OSError, ValueError, RuntimeError, ServiceError, EvidenceStorageFailure):
        return []
    run.result_payload = {**(run.result_payload or {}), 'vision_evidence_ids': [candidate['evidence_id']]}
    service.session.commit()
    return [
        {'type': 'text', 'text': 'VISION_INPUT: case_id=' + candidate['case_id'] + '; evidence_id=' + candidate['evidence_id']
         + '。这是该客户已授权且通过结构检查的原图。只描述可见外观，不诊断内部故障；模糊时要求补拍。'},
        {'type': 'image_url', 'image_url': {'url': 'data:' + media_type + ';base64,' + base64.b64encode(raw).decode('ascii'), 'detail': 'low'}},
    ]
