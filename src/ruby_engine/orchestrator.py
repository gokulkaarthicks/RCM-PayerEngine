from datetime import datetime, timedelta, timezone

from .audit import AuditWriter
from .config import EngineConfig
from .domain import WorkItem, WorkflowState
from .gateways import PayerGateway
from .policies import ApiPacer, ChannelPolicy, RetryPolicy
from .store import StateStore

SUBMISSION_ACTIONS = {
    "corrected_claim_submission",
    "appeal_submission",
}

PRIOR_SUBMISSION_STATES = {
    WorkflowState.IN_PROGRESS,
    WorkflowState.AWAITING_EXTERNAL_RESPONSE,
    WorkflowState.RETRY_SCHEDULED,
}

class Orchestrator:
    def __init__(
        self,
        config: EngineConfig,
        gateway: PayerGateway,
        store: StateStore,
        channel_policy: ChannelPolicy,
        retry_policy: RetryPolicy,
        api_pacer: ApiPacer,
        audit_writer: AuditWriter,
    ):
        self.config = config
        self.gateway = gateway
        self.store = store
        self.channel_policy = channel_policy
        self.retry_policy = retry_policy
        self.api_pacer = api_pacer
        self.audit_writer = audit_writer
        self.retry_count = 0

    def execute_action(
        self,
        item: WorkItem,
        channel: str,
        attempt: int,
        at_minute: int,
    ) -> dict:
        if item.action == "claim_status_inquiry":
            return self.gateway.claim_status(
                item=item,
                channel=channel,
                attempt=attempt,
                at_minute=at_minute,
            )

        if item.action in SUBMISSION_ACTIONS:
            return self.gateway.submit(
                item=item,
                channel=channel,
                attempt=attempt,
                at_minute=at_minute,
            )

        if item.action == "document_retrieval":
            return self.gateway.retrieve_document(
                item=item,
                attempt=attempt,
            )

        if item.action == "payer_followup_call":
            return self.gateway.ivr_call(
                item=item,
                attempt=attempt,
            )

        raise ValueError(
            f"Unsupported action: {item.action}"
        )
    

    def process_item(
        self,
        item: WorkItem,
    ) -> dict:
        state = self.store.get_or_create(item.id)

        terminal_states = {
            "completed",
            "needs_human_review",
            "warm_handoff_ready",
            "permanently_failed",
            "cancelled_or_superseded",
        }

        if state.current_state.value in terminal_states:
            return {
                "skipped": True,
                "reason": "work item already terminal",
            }
        
        if state.current_state == WorkflowState.AWAITING_EXTERNAL_RESPONSE:
            return {
                "skipped": True,
                "reason": "awaiting external response",
            }

        recovered = self._resume_submission(item, state)
        if recovered is not None:
            return recovered

        channel = self.channel_policy.choose_channel(
            action=item.action,
            payer_id=item.payer,
            config=self.config,
        )

        if channel is None:
            state.current_state = WorkflowState.NEEDS_HUMAN_REVIEW
            state.human_required = True
            state.reason = "no supported channel available"
            self.store.save(state)

            return {
                "skipped": True,
                "reason": state.reason,
            }

        is_retry = (
            state.current_state == WorkflowState.RETRY_SCHEDULED
        )
        not_before = (
            self.retry_policy.next_minute(state.at_minute)
            if is_retry
            else 0
        )

        state.current_state = WorkflowState.IN_PROGRESS
        state.channel = channel
        state.attempt += 1

        at_minute = self.api_pacer.next_minute(
            payer_id=item.payer,
            channel=channel,
            config=self.config,
            not_before=not_before,
        )

        state.at_minute = at_minute
        self.store.save(state)

        result = self.execute_action(
            item=item,
            channel=channel,
            attempt=state.attempt,
            at_minute=at_minute,
        )

        return result

    
    def process_result(
        self,
        item: WorkItem,
        result: dict,
    ) -> None:
        state = self.store.get_or_create(item.id)

        connector_result = result["result"]

        state.last_result = connector_result
        state.external_ref = result.get("external_ref")
        state.reason = result.get("detail", "")

        if connector_result == "SUCCESS":
            state.current_state = WorkflowState.COMPLETED

        elif connector_result == "RETRYABLE":
            if self.retry_policy.can_retry(state.attempt):
                state.current_state = WorkflowState.RETRY_SCHEDULED
            else:
                state.current_state = WorkflowState.PERMANENTLY_FAILED

        elif connector_result == "WARM_HANDOFF":
            state.current_state = WorkflowState.WARM_HANDOFF_READY
            state.human_required = True

        elif connector_result == "PERMANENT_FAILURE":
            state.current_state = WorkflowState.PERMANENTLY_FAILED

        elif connector_result == "AMBIGUOUS":
            state.current_state = WorkflowState.AWAITING_EXTERNAL_RESPONSE
            self.store.save(state)

            self.audit_writer.write_event(
                item=item,
                state=state,
                actor="automation",
                ts=self.simulated_timestamp(state.at_minute),
                result=connector_result,
                detail=state.reason,
            )

            if item.action in SUBMISSION_ACTIONS:
                self.handle_ambiguous_submission(item)

            return
        
        elif connector_result in {
            "NEEDS_HUMAN",
            "BLOCKED_MISSING_ARTIFACT",
            "CONFLICT",
            "CHANNEL_UNAVAILABLE",
            "INVALID_CHANNEL_FOR_ACTION",
        }:
            state.current_state = WorkflowState.NEEDS_HUMAN_REVIEW
            state.human_required = True

        self.store.save(state)

        self.audit_writer.write_event(
            item=item,
            state=state,
            actor="automation",
            ts=self.simulated_timestamp(state.at_minute),
            result=connector_result,
            detail=state.reason,
        )

    
    def handle_ambiguous_submission(
        self,
        item: WorkItem,
    ) -> None:
        state = self.store.get_or_create(item.id)

        status = self.gateway.submission_status(
            tenant=item.tenant,
            idempotency_key=item.idempotency_key,
        )

        if status.get("on_file"):
            state.current_state = WorkflowState.COMPLETED
            state.external_ref = status.get("external_ref")
            state.reason = (
                "submission verified after ambiguous response"
            )
        else:
            if self.retry_policy.can_retry(state.attempt):
                state.current_state = WorkflowState.RETRY_SCHEDULED
                state.reason = (
                    "submission not confirmed after ambiguous response"
                )
            else:
                state.current_state = WorkflowState.PERMANENTLY_FAILED
                state.reason = (
                    "submission not confirmed and retry limit reached"
                )

        self.store.save(state)

        self.audit_writer.write_event(
            item=item,
            state=state,
            actor="automation",
            ts=self.simulated_timestamp(state.at_minute),
            result=status["result"],
            detail=state.reason,
        )


    def _resume_submission(
        self,
        item: WorkItem,
        state,
    ) -> dict | None:
        if item.action not in SUBMISSION_ACTIONS:
            return None
        if state.current_state not in PRIOR_SUBMISSION_STATES:
            return None

        status = self.gateway.submission_status(
            tenant=item.tenant,
            idempotency_key=item.idempotency_key,
        )
        if status.get("on_file"):
            return {
                "result": "SUCCESS",
                "external_ref": status.get("external_ref"),
                "detail": (
                    status.get("detail")
                    or "submission already on file"
                ),
            }

        if (
            state.current_state == WorkflowState.IN_PROGRESS
            and state.channel
            and state.attempt > 0
        ):
            return self.execute_action(
                item=item,
                channel=state.channel,
                attempt=state.attempt,
                at_minute=state.at_minute,
            )

        return None

    def record_cancelled_items(
        self,
        cancelled_items: dict[str, str],
        work_items: list[WorkItem],
    ) -> None:
        items_by_id = {
            item.id: item
            for item in work_items
        }

        for work_item_id, reason in cancelled_items.items():
            state = self.store.get_or_create(work_item_id)

            if state.current_state == WorkflowState.CANCELLED_OR_SUPERSEDED:
                continue

            item = items_by_id[work_item_id]
            state.current_state = (
                WorkflowState.CANCELLED_OR_SUPERSEDED
            )
            state.reason = reason
            self.store.save(state)

            self.audit_writer.write_event(
                item=item,
                state=state,
                actor="automation",
                ts=self.simulated_timestamp(state.at_minute),
                result=None,
                detail=reason,
            )

    
    def run(
        self,
        items: list[WorkItem],
    ) -> None:

        for item in items:
            result = self.process_item(
                item=item,
            )

            if result.get("skipped"):
                continue

            self.process_result(
                item=item,
                result=result,
            )

            state = self.store.get_or_create(item.id)

            while (
                state.current_state
                == WorkflowState.RETRY_SCHEDULED
            ):
                if not self.retry_policy.can_retry(state.attempt):
                    break

                previous_attempt = state.attempt
                retry_result = self.process_item(
                    item=item,
                )

                if retry_result.get("skipped"):
                    break

                self.retry_count += 1
                self.process_result(
                    item=item,
                    result=retry_result,
                )
                state = self.store.get_or_create(item.id)

                if (
                    state.current_state
                    == WorkflowState.RETRY_SCHEDULED
                    and state.attempt <= previous_attempt
                ):
                    break
    
    def simulated_timestamp(self, at_minute: int) -> str:
        base = datetime.fromisoformat(
            self.gateway.case_as_of.replace("Z", "+00:00")
        )
        timestamp = base + timedelta(minutes=at_minute)

        return timestamp.astimezone(timezone.utc).isoformat(
            timespec="seconds"
        ).replace("+00:00", "Z")