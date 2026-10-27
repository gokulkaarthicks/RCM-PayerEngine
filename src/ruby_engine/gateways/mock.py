import importlib.util
from pathlib import Path
from typing import Any

from ..domain import WorkItem
from .base import PayerGateway

PAYER_LEDGERS = (
    "external_side_effect_ledger.jsonl",
    "connector_interaction_ledger.jsonl",
)


def durable_output_exists(
    output_dir: str,
    state_db_name: str,
) -> bool:
    root = Path(output_dir)
    names = (state_db_name, *PAYER_LEDGERS)
    return any((root / name).exists() for name in names)


class MockPayerGatewayAdapter(PayerGateway):
    def __init__(
        self,
        kit_dir: str,
        output_dir: str,
        fresh: bool = True,
    ):
        kit_path = Path(kit_dir)
        output_path = Path(output_dir)

        output_path.mkdir(
            parents=True,
            exist_ok=True,
        )

        mock_path = kit_path / "mock_connectors.py"

        spec = importlib.util.spec_from_file_location(
            "mock_connectors",
            mock_path,
        )

        if spec is None or spec.loader is None:
            raise RuntimeError(
                "Unable to load mock_connectors.py"
            )

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        side_effect_ledger = (
            output_path
            / "external_side_effect_ledger.jsonl"
        )

        interaction_ledger = (
            output_path
            / "connector_interaction_ledger.jsonl"
        )

        self._gateway = module.MockPayerGateway(
            starter_kit_dir=str(kit_path),
            side_effect_ledger=str(side_effect_ledger),
            interaction_ledger=str(interaction_ledger),
            fresh=fresh,
        )

        self._case_as_of = module.CASE_AS_OF

    @property
    def case_as_of(self) -> str:
        return self._case_as_of

    def claim_status(
        self,
        item: WorkItem,
        channel: str,
        attempt: int,
        at_minute: int,
    ) -> dict[str, Any]:
        return self._gateway.claim_status(
            item.__dict__,
            channel=channel,
            attempt=attempt,
            at_minute=at_minute,
        )

    def submit(
        self,
        item: WorkItem,
        channel: str,
        attempt: int,
        at_minute: int,
    ) -> dict[str, Any]:
        return self._gateway.submit(
            item.__dict__,
            channel=channel,
            idempotency_key=item.idempotency_key,
            action=item.action,
            attempt=attempt,
            at_minute=at_minute,
        )

    def submission_status(
        self,
        tenant: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self._gateway.submission_status(
            tenant,
            idempotency_key,
        )

    def retrieve_document(
        self,
        item: WorkItem,
        attempt: int,
    ) -> dict[str, Any]:
        return self._gateway.retrieve_document(
            item.__dict__,
            attempt=attempt,
        )

    def ivr_call(
        self,
        item: WorkItem,
        attempt: int,
    ) -> dict[str, Any]:
        return self._gateway.ivr_call(
            item.__dict__,
            attempt=attempt,
        )