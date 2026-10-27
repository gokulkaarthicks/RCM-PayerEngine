from dataclasses import dataclass
from collections import defaultdict
from .config import EngineConfig

CHANNEL_CAPABILITY_FIELD = {
    "api": "supports_api_276_277",
    "portal": "supports_portal",
    "fax": "supports_fax",
    "ivr": "supports_ivr",
    "clearinghouse": "supports_clearinghouse_837",
    "doc": None,
}

@dataclass(frozen=True)
class ChannelPolicy:
    def choose_channel(
        self,
        action: str,
        payer_id: str,
        config: EngineConfig,
    ) -> str | None:
        valid_channels = config.action_channels.get(action, [])
        payer = config.payer_capabilities.get(payer_id)

        if payer is None:
            return None

        for channel in valid_channels:
            capability_field = CHANNEL_CAPABILITY_FIELD[channel]

            if capability_field is None:
                return channel

            if getattr(payer, capability_field):
                return channel

        return None


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 2
    backoff_minutes: int = 1

    def can_retry(self, attempt: int) -> bool:
        return attempt < self.max_attempts

    def next_minute(self, failed_at_minute: int) -> int:
        return failed_at_minute + self.backoff_minutes


class ApiPacer:
    def __init__(self):
        self._api_calls: dict[tuple[str, int], int] = defaultdict(int)

    def next_minute(
        self,
        payer_id: str,
        channel: str,
        config: EngineConfig,
        not_before: int = 0,
    ) -> int:
        if channel != "api":
            return not_before

        payer = config.payer_capabilities[payer_id]
        limit = payer.api_throttle_per_min

        if limit <= 0:
            return not_before

        at_minute = not_before
        while self._api_calls[(payer_id, at_minute)] >= limit:
            at_minute += 1

        self._api_calls[(payer_id, at_minute)] += 1
        return at_minute