import csv
import json
from dataclasses import dataclass
from pathlib import Path

from .domain import WorkItem


@dataclass(frozen=True)
class PayerCapability:
    payer_id: str
    payer_name: str
    supports_api_276_277: bool
    supports_portal: bool
    supports_fax: bool
    supports_ivr: bool
    supports_clearinghouse_837: bool
    api_throttle_per_min: int
    portal_session_minutes: int
    quirks: str


@dataclass(frozen=True)
class EngineConfig:
    work_items: list[WorkItem]
    payer_capabilities: dict[str, PayerCapability]
    action_channels: dict[str, list[str]]


def _to_bool(value: str) -> bool:
    return value.strip().upper() == "Y"


def _is_jsonl_comment(line: str) -> bool:
    stripped = line.strip()
    return not stripped or stripped.startswith("//") or stripped.startswith("#")


def load_work_items(kit_dir: Path) -> list[WorkItem]:
    path = kit_dir / "work_items.jsonl"

    items: list[WorkItem] = []

    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if _is_jsonl_comment(line):
                continue

            data = json.loads(line)
            items.append(WorkItem(**data))

    return items


def load_payer_capabilities(
    kit_dir: Path,
) -> dict[str, PayerCapability]:
    path = kit_dir / "payer_capability_matrix.csv"

    capabilities: dict[str, PayerCapability] = {}

    with path.open("r", encoding="utf-8") as file:
        reader = csv.DictReader(file)

        for row in reader:
            payer = PayerCapability(
                payer_id=row["payer_id"],
                payer_name=row["payer_name"],
                supports_api_276_277=_to_bool(
                    row["supports_api_276_277"]
                ),
                supports_portal=_to_bool(
                    row["supports_portal"]
                ),
                supports_fax=_to_bool(
                    row["supports_fax"]
                ),
                supports_ivr=_to_bool(
                    row["supports_ivr"]
                ),
                supports_clearinghouse_837=_to_bool(
                    row["supports_clearinghouse_837"]
                ),
                api_throttle_per_min=int(
                    row["api_throttle_per_min"]
                ),
                portal_session_minutes=int(
                    row["portal_session_minutes"]
                ),
                quirks=row["quirks"],
            )

            capabilities[payer.payer_id] = payer

    return capabilities


def load_action_channels(
    kit_dir: Path,
) -> dict[str, list[str]]:
    path = kit_dir / "action_channel_map.csv"

    action_channels: dict[str, list[str]] = {}

    with path.open("r", encoding="utf-8") as file:
        reader = csv.DictReader(file)

        for row in reader:
            action_channels[row["action"]] = (
                row["valid_channels"].split("|")
            )

    return action_channels


def load_engine_config(kit_dir: str) -> EngineConfig:
    path = Path(kit_dir)

    return EngineConfig(
        work_items=load_work_items(path),
        payer_capabilities=load_payer_capabilities(path),
        action_channels=load_action_channels(path),
    )