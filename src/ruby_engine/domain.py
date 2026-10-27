from dataclasses import dataclass
from enum import Enum
from typing import Optional


class WorkflowState(str, Enum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    AWAITING_EXTERNAL_RESPONSE = "awaiting_external_response"
    RETRY_SCHEDULED = "retry_scheduled"
    NEEDS_HUMAN_REVIEW = "needs_human_review"
    WARM_HANDOFF_READY = "warm_handoff_ready"
    COMPLETED = "completed"
    PERMANENTLY_FAILED = "permanently_failed"
    CANCELLED_OR_SUPERSEDED = "cancelled_or_superseded"


class ConnectorResult(str, Enum):
    SUCCESS = "SUCCESS"
    AMBIGUOUS = "AMBIGUOUS"
    RETRYABLE = "RETRYABLE"
    NEEDS_HUMAN = "NEEDS_HUMAN"
    PERMANENT_FAILURE = "PERMANENT_FAILURE"
    WARM_HANDOFF = "WARM_HANDOFF"
    BLOCKED_MISSING_ARTIFACT = "BLOCKED_MISSING_ARTIFACT"
    CONFLICT = "CONFLICT"
    CHANNEL_UNAVAILABLE = "CHANNEL_UNAVAILABLE"
    INVALID_CHANNEL_FOR_ACTION = "INVALID_CHANNEL_FOR_ACTION"


class ActionType(str, Enum):
    CLAIM_STATUS_INQUIRY = "claim_status_inquiry"
    CORRECTED_CLAIM_SUBMISSION = "corrected_claim_submission"
    APPEAL_SUBMISSION = "appeal_submission"
    DOCUMENT_RETRIEVAL = "document_retrieval"
    PAYER_FOLLOWUP_CALL = "payer_followup_call"


@dataclass(frozen=True)
class WorkItem:
    schema_version: str
    work_item_version: int
    id: str
    tenant: str
    encounter: str
    payer: str
    action: str
    priority: str
    deadline: str
    claim_number: Optional[str]
    member_id: Optional[str]
    npi: Optional[str]
    dos: Optional[str]
    billed: float
    required_artifacts: list[str]
    provided_artifacts: list[str]
    blocked_by: list[str]
    source: str
    idempotency_key: str
    created_at: str
    available_at: str
    scenario: str
    supersedes: Optional[str] = None


@dataclass
class WorkItemState:
    work_item_id: str
    current_state: WorkflowState = WorkflowState.QUEUED
    attempt: int = 0
    at_minute: int = 0
    channel: Optional[str] = None
    external_ref: Optional[str] = None
    last_result: Optional[str] = None
    reason: str = ""
    human_required: bool = False