from abc import ABC, abstractmethod
from typing import Any

from ..domain import WorkItem


class PayerGateway(ABC):
    @property
    @abstractmethod
    def case_as_of(self) -> str:
        pass

    @abstractmethod
    def claim_status(
        self,
        item: WorkItem,
        channel: str,
        attempt: int,
        at_minute: int,
    ) -> dict[str, Any]:
        pass

    @abstractmethod
    def submit(
        self,
        item: WorkItem,
        channel: str,
        attempt: int,
        at_minute: int,
    ) -> dict[str, Any]:
        pass

    @abstractmethod
    def submission_status(
        self,
        tenant: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        pass

    @abstractmethod
    def retrieve_document(
        self,
        item: WorkItem,
        attempt: int,
    ) -> dict[str, Any]:
        pass

    @abstractmethod
    def ivr_call(
        self,
        item: WorkItem,
        attempt: int,
    ) -> dict[str, Any]:
        pass