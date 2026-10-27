from dataclasses import dataclass
from .domain import WorkItem

@dataclass(frozen=True)
class ReconciliationResult:
    active_items: list[WorkItem]
    cancelled_items: dict[str, str]


class BatchReconciler:
    def reconcile(
        self,
        items: list[WorkItem],
    ) -> ReconciliationResult:
        cancelled: dict[str, str] = {}

        superseded_ids = self._find_superseded_ids(items)

        for item_id in superseded_ids:
            cancelled[item_id] = "superseded by newer work item"

        remaining = [
            item for item in items
            if item.id not in superseded_ids
        ]

        remaining = self._dedupe_by_idempotency(
            remaining,
            cancelled,
        )

        remaining = self._dedupe_by_encounter_action(
            remaining,
            cancelled,
        )

        return ReconciliationResult(
            active_items=remaining,
            cancelled_items=cancelled,
        )

    def _find_superseded_ids(
        self,
        items: list[WorkItem],
    ) -> set[str]:
        return {
            item.supersedes
            for item in items
            if item.supersedes is not None
        }

    def _dedupe_by_idempotency(
        self,
        items: list[WorkItem],
        cancelled: dict[str, str],
    ) -> list[WorkItem]:
        seen: set[tuple[str, str]] = set()
        result: list[WorkItem] = []

        for item in sorted(items, key=lambda x: x.created_at):
            key = (
                item.tenant,
                item.idempotency_key,
            )

            if key in seen:
                cancelled[item.id] = (
                    "duplicate tenant-scoped idempotency key"
                )
                continue

            seen.add(key)
            result.append(item)

        return result

    def _dedupe_by_encounter_action(
        self,
        items: list[WorkItem],
        cancelled: dict[str, str],
    ) -> list[WorkItem]:
        seen: set[tuple[str, str, str]] = set()
        result: list[WorkItem] = []

        for item in sorted(items, key=lambda x: x.created_at):
            key = (
                item.tenant,
                item.encounter,
                item.action,
            )

            if key in seen:
                cancelled[item.id] = (
                    "duplicate encounter and action"
                )
                continue

            seen.add(key)
            result.append(item)

        return result