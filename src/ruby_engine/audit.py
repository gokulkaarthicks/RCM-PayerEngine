import json
import uuid
from pathlib import Path

from .domain import WorkItem, WorkItemState


class AuditWriter:
    def __init__(self, output_dir: str):
        self.path = Path(output_dir) / "audit_log.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write_event(
        self,
        item: WorkItem,
        state: WorkItemState,
        actor: str,
        ts: str,
        result: str | None = None,
        detail: str = "",
        artifacts: list[str] | None = None,
        human_override: dict | None = None,
    ) -> None:
        event = {
            "event_id": str(uuid.uuid4()),
            "correlation_id": f"corr-{item.id}",
            "work_item_id": item.id,
            "tenant": item.tenant,
            "ts": ts,
            "actor": actor,
            "schema_version": item.schema_version,
            "workflow_version": "1.0",
            "action": item.action,
            "channel": state.channel,
            "attempt": state.attempt,
            "result": result,
            "external_ref": state.external_ref,
            "artifacts": artifacts or [],
            "human_override": human_override,
            "disposition": state.current_state.value,
            "detail": detail,
        }

        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event) + "\n")