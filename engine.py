import argparse
import sys
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from ruby_engine.audit import AuditWriter
from ruby_engine.config import load_engine_config
from ruby_engine.gateways import MockPayerGatewayAdapter
from ruby_engine.gateways.mock import durable_output_exists
from ruby_engine.orchestrator import Orchestrator
from ruby_engine.policies import ApiPacer, ChannelPolicy, RetryPolicy
from ruby_engine.reconciler import BatchReconciler
from ruby_engine.store import StateStore
from ruby_engine.summary import SummaryWriter


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kit", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    config = load_engine_config(args.kit)
    reconciliation = BatchReconciler().reconcile(
        config.work_items
    )

    output_dir = Path(args.out)
    output_dir.mkdir(parents=True, exist_ok=True)

    state_db_name = "work_item_state.db"
    fresh = not durable_output_exists(
        args.out,
        state_db_name,
    )
    store = StateStore(str(output_dir / state_db_name))
    gateway = MockPayerGatewayAdapter(
        kit_dir=args.kit,
        output_dir=args.out,
        fresh=fresh,
    )
    channel_policy = ChannelPolicy()
    retry_policy = RetryPolicy()
    api_pacer = ApiPacer()
    audit_writer = AuditWriter(args.out)
    summary_writer = SummaryWriter(args.out)

    orchestrator = Orchestrator(
        config=config,
        gateway=gateway,
        store=store,
        channel_policy=channel_policy,
        retry_policy=retry_policy,
        api_pacer=api_pacer,
        audit_writer=audit_writer,
    )

    orchestrator.record_cancelled_items(
        cancelled_items=reconciliation.cancelled_items,
        work_items=config.work_items,
    )
    orchestrator.run(reconciliation.active_items)

    summary_writer.write(
        store=store,
        work_items=config.work_items,
        case_as_of=gateway.case_as_of,
        retry_count=orchestrator.retry_count,
        duplicates_prevented=len(reconciliation.cancelled_items),
    )

    submission_dir = Path("submission")
    submission_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copy2(
        output_dir / "audit_log.jsonl",
        submission_dir / "audit_log.jsonl",
    )

    shutil.copy2(
        output_dir / "run_summary.json",
        submission_dir / "run_summary.json",
    )


if __name__ == "__main__":
    main()
