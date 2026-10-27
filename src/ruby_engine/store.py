import sqlite3
from pathlib import Path

from .domain import WorkItemState, WorkflowState


class StateStore:
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS work_item_state (
                    work_item_id TEXT PRIMARY KEY,
                    current_state TEXT NOT NULL,
                    attempt INTEGER NOT NULL DEFAULT 0,
                    at_minute INTEGER NOT NULL DEFAULT 0,
                    channel TEXT,
                    external_ref TEXT,
                    last_result TEXT,
                    reason TEXT NOT NULL DEFAULT '',
                    human_required INTEGER NOT NULL DEFAULT 0
                )
                """
            )

    def get(
        self,
        work_item_id: str,
    ) -> WorkItemState | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    work_item_id,
                    current_state,
                    attempt,
                    at_minute,
                    channel,
                    external_ref,
                    last_result,
                    reason,
                    human_required
                FROM work_item_state
                WHERE work_item_id = ?
                """,
                (work_item_id,),
            ).fetchone()

        if row is None:
            return None

        return WorkItemState(
            work_item_id=row["work_item_id"],
            current_state=WorkflowState(row["current_state"]),
            attempt=row["attempt"],
            at_minute=row["at_minute"],
            channel=row["channel"],
            external_ref=row["external_ref"],
            last_result=row["last_result"],
            reason=row["reason"],
            human_required=bool(row["human_required"]),
        )

    def save(
        self,
        state: WorkItemState,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO work_item_state (
                    work_item_id,
                    current_state,
                    attempt,
                    at_minute,
                    channel,
                    external_ref,
                    last_result,
                    reason,
                    human_required
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)

                ON CONFLICT(work_item_id)
                DO UPDATE SET
                    current_state = excluded.current_state,
                    attempt = excluded.attempt,
                    at_minute = excluded.at_minute,
                    channel = excluded.channel,
                    external_ref = excluded.external_ref,
                    last_result = excluded.last_result,
                    reason = excluded.reason,
                    human_required = excluded.human_required
                """,
                (
                    state.work_item_id,
                    state.current_state.value,
                    state.attempt,
                    state.at_minute,
                    state.channel,
                    state.external_ref,
                    state.last_result,
                    state.reason,
                    int(state.human_required),
                ),
            )

    def get_or_create(
        self,
        work_item_id: str,
    ) -> WorkItemState:
        existing = self.get(work_item_id)

        if existing is not None:
            return existing

        state = WorkItemState(
            work_item_id=work_item_id,
        )

        self.save(state)

        return state

    def get_all(self) -> list[WorkItemState]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    work_item_id,
                    current_state,
                    attempt,
                    at_minute,
                    channel,
                    external_ref,
                    last_result,
                    reason,
                    human_required
                FROM work_item_state
                """
            ).fetchall()

        return [
            WorkItemState(
                work_item_id=row["work_item_id"],
                current_state=WorkflowState(
                    row["current_state"]
                ),
                attempt=row["attempt"],
                at_minute=row["at_minute"],
                channel=row["channel"],
                external_ref=row["external_ref"],
                last_result=row["last_result"],
                reason=row["reason"],
                human_required=bool(
                    row["human_required"]
                ),
            )
            for row in rows
        ]