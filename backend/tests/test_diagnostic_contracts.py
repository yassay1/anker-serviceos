from uuid import uuid4

import pytest
from pydantic import ValidationError

from serviceos_api.application.diagnostic_contracts import (
    DiagnosticExperience,
    DiagnosticEvidenceRef,
    DiagnosticResult,
    DiagnosticTaskInput,
    validate_diagnostic_result,
)


def test_diagnostic_result_accepts_only_referenced_hypotheses():
    task_id = uuid4()
    evidence_id = uuid4()
    task = DiagnosticTaskInput(
        task_id=task_id,
        conversation_id=uuid4(),
        goal="查明用户报告的无法充电问题",
        evidence_refs=[DiagnosticEvidenceRef(ref_id=str(evidence_id), ref_kind="CASE_EVIDENCE",
                                             summary="客户报告连接后没有充电")],
    )
    result = DiagnosticResult(
        task_id=task_id,
        assessment="可能是连接线或输入端口问题",
        evidence_refs=[{"ref_id": str(evidence_id), "supports": "用户报告连接后未充电"}],
        unknowns=["尚未确认线材类型"],
        next_step={"kind": "ASK_CUSTOMER", "summary": "确认线材类型", "question": {"prompt": "当前使用的线材是什么类型？"}},
        staff_summary="这是尚未核验的诊断假设。",
    )

    validated = validate_diagnostic_result(result, task)

    assert validated.certainty == "HYPOTHESIS"
    assert validated.evidence_refs[0].ref_id == str(evidence_id)


def test_diagnostic_result_rejects_untrusted_task_and_evidence_references():
    task_id = uuid4()
    task = DiagnosticTaskInput(task_id=task_id, conversation_id=uuid4(), goal="排查", evidence_refs=[])
    result = DiagnosticResult(
        task_id=uuid4(),
        assessment="已经确认端口损坏",
        evidence_refs=[{"ref_id": str(uuid4()), "supports": "不受授权的设备事实"}],
        next_step={"kind": "NO_ACTION", "summary": "结束"},
        staff_summary="无来源。",
    )

    with pytest.raises(ValueError, match="diagnostic_result_task_mismatch"):
        validate_diagnostic_result(result, task)

    result.task_id = task_id
    with pytest.raises(ValueError, match="diagnostic_result_reference_not_authorized"):
        validate_diagnostic_result(result, task)


@pytest.mark.parametrize("payload", [
    {"task_id": str(uuid4()), "conversation_id": str(uuid4()), "goal": "x" * 1001},
    {"task_id": str(uuid4()), "conversation_id": str(uuid4()), "goal": "排查", "tenant_id": str(uuid4())},
    {"task_id": str(uuid4()), "conversation_id": str(uuid4()), "goal": "排查",
     "evidence_refs": [{"ref_id": str(uuid4()), "ref_kind": "PRIVATE_MESSAGE"}]},
])
def test_diagnostic_task_input_rejects_oversize_and_untrusted_fields(payload):
    with pytest.raises(ValidationError):
        DiagnosticTaskInput.model_validate(payload)


def test_diagnostic_result_rejects_unbounded_or_unknown_output_fields():
    with pytest.raises(ValidationError):
        DiagnosticResult.model_validate({
            "task_id": str(uuid4()), "assessment": "x" * 2001,
            "next_step": {"kind": "NO_ACTION", "summary": "完成"},
            "chain_of_thought": "private reasoning",
        })


@pytest.mark.parametrize("next_step", [
    {"kind": "ASK_CUSTOMER", "summary": "询问"},
    {"kind": "NO_ACTION", "summary": "结束", "question": {"prompt": "意外提问"}},
    {"kind": "ASK_CUSTOMER", "summary": "询问", "question": {"prompt": "点此访问 https://example.com"}},
    {"kind": "ASK_CUSTOMER", "summary": "询问", "question": {"prompt": "选择", "options": ["唯一选项"]}},
])
def test_diagnostic_customer_question_is_typed_and_safe(next_step):
    with pytest.raises(ValidationError):
        DiagnosticResult(task_id=uuid4(), assessment="待核验假设", next_step=next_step,
                         staff_summary="供客服审阅的假设。")


def test_diagnostic_context_accepts_only_two_typed_reviewed_experience_references():
    candidate = DiagnosticExperience(
        candidate_id=uuid4(), candidate_version=2, source_case_id=uuid4(), source_verification_id=uuid4(),
        issue_type="no-charge", title="检查供电连接", applicable_models=["A3134"], symptoms=["无法充电"],
        required_evidence=["适配器状态"], steps=["检查线材是否牢固"],
        success_criteria="客户确认恢复正常", failure_exit="停止测试并联系人工客服",
    )
    task = DiagnosticTaskInput(
        task_id=uuid4(), conversation_id=uuid4(), goal="核对供电问题",
        experience_examples=[candidate],
        evidence_refs=[{"ref_id": str(candidate.candidate_id), "ref_kind": "EXPERIENCE_CANDIDATE",
                        "summary": candidate.title}],
    )
    assert task.experience_examples[0].candidate_version == 2
    with pytest.raises(ValidationError):
        DiagnosticTaskInput(task_id=uuid4(), conversation_id=uuid4(), goal="核对",
                            experience_examples=[candidate, candidate, candidate])
