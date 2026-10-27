import json
from pathlib import Path

from .domain import WorkItem, WorkflowState
from .store import StateStore


TERMINAL_STATES = {
    WorkflowState.NEEDS_HUMAN_REVIEW,
    WorkflowState.WARM_HANDOFF_READY,
    WorkflowState.COMPLETED,
    WorkflowState.PERMANENTLY_FAILED,
    WorkflowState.CANCELLED_OR_SUPERSEDED,
}


class SummaryWriter:
    def __init__(self, output_dir: str):
        self.path = Path(output_dir) / "run_summary.json"
        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

    def write(
        self,
        store: StateStore,
        work_items: list[WorkItem],
        case_as_of: str,
        retry_count: int,
        duplicates_prevented: int,
    ) -> None:
        states = store.get_all()

        state_by_id = {
            state.work_item_id: state
            for state in states
        }

        items = []

        for work_item in work_items:
            state = state_by_id[work_item.id]

            terminal_disposition = (
                state.current_state.value
                if state.current_state in TERMINAL_STATES
                else None
            )

            items.append(
                {
                    "work_item_id": work_item.id,
                    "tenant": work_item.tenant,
                    "current_state": state.current_state.value,
                    "terminal_disposition": terminal_disposition,
                    "attempts": state.attempt,
                    "external_ref": state.external_ref,
                    "reason": state.reason,
                }
            )

        completed = sum(
            1
            for state in states
            if state.current_state
            == WorkflowState.COMPLETED
        )

        touchless_completed = sum(
            1
            for state in states
            if (
                state.current_state
                == WorkflowState.COMPLETED
                and not state.human_required
            )
        )

        failures = sum(
            1
            for state in states
            if state.current_state
            == WorkflowState.PERMANENTLY_FAILED
        )

        warm_handoffs = sum(
            1
            for state in states
            if state.current_state
            == WorkflowState.WARM_HANDOFF_READY
        )

        human_action_count = sum(
            1
            for state in states
            if state.human_required
        )

        total_items = len(work_items)

        completion_rate = (
            completed / total_items
            if total_items
            else 0.0
        )

        touchless_completion_rate = (
            touchless_completed / total_items
            if total_items
            else 0.0
        )

        summary = {
            "case_as_of": case_as_of,
            "items": items,
            "metrics": {
                "completion_rate": completion_rate,
                "touchless_completion_rate": (
                    touchless_completion_rate
                ),
                "human_minutes": human_action_count,
                "retry_count": retry_count,
                "failure_count": failures,
                "duplicates_prevented": duplicates_prevented,
                "warm_handoffs_ready": warm_handoffs,
            },
        }

        with self.path.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                summary,
                file,
                indent=2,
            )