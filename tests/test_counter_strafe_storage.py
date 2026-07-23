from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import storage


class CounterStrafeStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test_coach.sqlite"
        self._connections: list[sqlite3.Connection] = []
        self._db_path_patcher = patch.object(storage, "DB_PATH", self.db_path)
        self._connect_patcher = patch.object(
            storage,
            "_connect",
            side_effect=self._tracked_connect,
        )
        self._db_path_patcher.start()
        self._connect_patcher.start()
        storage.init_db()

    def tearDown(self) -> None:
        for conn in self._connections:
            conn.close()
        self._connections.clear()
        self._connect_patcher.stop()
        self._db_path_patcher.stop()
        self._tmpdir.cleanup()

    def _tracked_connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        self._connections.append(conn)
        return conn

    def _valid_kwargs(self, **overrides):
        payload = {
            "nickname": "Jurses",
            "session_date": "2026-07-23",
            "drill_name": "Counter-Strafe Map",
            "kills": 500,
            "avg_kill_score": 69.2,
            "avg_speed": 14.3,
            "avg_timing_ms": 207.0,
            "avg_technique_pct": 50.8,
            "hit_accuracy_pct": 51.5,
        }
        payload.update(overrides)
        return payload

    def test_migration_is_rerunnable(self) -> None:
        storage.init_db()
        storage.init_db()

        session_id = storage.save_counter_strafe_session(**self._valid_kwargs())
        self.assertGreater(session_id, 0)
        rows = storage.list_counter_strafe_sessions("Jurses", limit=1)
        self.assertEqual(len(rows), 1)

    def test_save_and_read_valid_session(self) -> None:
        session_id = storage.save_counter_strafe_session(**self._valid_kwargs())
        self.assertGreater(session_id, 0)

        rows = storage.list_counter_strafe_sessions("Jurses", limit=1)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["id"], session_id)
        self.assertEqual(row["nickname"], "jurses")
        self.assertEqual(row["session_date"], "2026-07-23")
        self.assertEqual(row["drill_name"], "Counter-Strafe Map")
        self.assertEqual(row["kills"], 500)
        self.assertEqual(row["avg_technique_pct"], 50.8)
        self.assertEqual(row["source"], storage.COUNTER_STRAFE_SOURCE_USER_ENTRY)

    def test_rejects_invalid_percentage(self) -> None:
        with self.assertRaises(storage.CounterStrafeSessionError):
            storage.save_counter_strafe_session(
                **self._valid_kwargs(avg_technique_pct=101.0)
            )
        with self.assertRaises(storage.CounterStrafeSessionError):
            storage.save_counter_strafe_session(
                **self._valid_kwargs(hit_accuracy_pct=-1.0)
            )

    def test_rejects_negative_timing_and_speed(self) -> None:
        with self.assertRaises(storage.CounterStrafeSessionError):
            storage.save_counter_strafe_session(
                **self._valid_kwargs(avg_timing_ms=-1.0)
            )
        with self.assertRaises(storage.CounterStrafeSessionError):
            storage.save_counter_strafe_session(
                **self._valid_kwargs(avg_speed=-0.1)
            )

    def test_rejects_zero_kills(self) -> None:
        with self.assertRaises(storage.CounterStrafeSessionError):
            storage.save_counter_strafe_session(**self._valid_kwargs(kills=0))

    def test_nickname_isolation(self) -> None:
        storage.save_counter_strafe_session(**self._valid_kwargs(nickname="Jurses"))
        storage.save_counter_strafe_session(
            **self._valid_kwargs(
                nickname="OtherPlayer",
                drill_name="Other Drill",
                session_date="2026-07-22",
            )
        )

        jurses_rows = storage.list_counter_strafe_sessions("Jurses", limit=10)
        other_rows = storage.list_counter_strafe_sessions("OtherPlayer", limit=10)

        self.assertEqual(len(jurses_rows), 1)
        self.assertEqual(jurses_rows[0]["nickname"], "jurses")
        self.assertEqual(len(other_rows), 1)
        self.assertEqual(other_rows[0]["nickname"], "otherplayer")

    def test_last_n_ordering_is_deterministic(self) -> None:
        storage.save_counter_strafe_session(
            **self._valid_kwargs(session_date="2026-07-21", drill_name="Drill A")
        )
        storage.save_counter_strafe_session(
            **self._valid_kwargs(session_date="2026-07-23", drill_name="Drill B")
        )
        storage.save_counter_strafe_session(
            **self._valid_kwargs(session_date="2026-07-23", drill_name="Drill C")
        )

        rows = storage.list_counter_strafe_sessions("Jurses", limit=2)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["session_date"], "2026-07-23")
        self.assertEqual(rows[0]["drill_name"], "Drill C")
        self.assertEqual(rows[1]["session_date"], "2026-07-23")
        self.assertEqual(rows[1]["drill_name"], "Drill B")

    def test_does_not_touch_real_db_path(self) -> None:
        real_db = Path(__file__).resolve().parent.parent / "data" / "db" / "coach.sqlite"
        self.assertNotEqual(self.db_path.resolve(), real_db.resolve())

    def test_accepts_valid_iso_date(self) -> None:
        session_id = storage.save_counter_strafe_session(
            **self._valid_kwargs(session_date="2026-07-23")
        )
        self.assertGreater(session_id, 0)

    def test_rejects_invalid_and_impossible_dates(self) -> None:
        invalid_dates = (
            "2026-02-30",
            "23-07-2026",
            "2026-07-23T10:00:00",
            "not-a-date",
        )
        for session_date in invalid_dates:
            with self.subTest(session_date=session_date):
                with self.assertRaises(storage.CounterStrafeSessionError):
                    storage.save_counter_strafe_session(
                        **self._valid_kwargs(session_date=session_date)
                    )

    def test_rejects_nan_and_infinity_for_metrics(self) -> None:
        metric_fields = (
            "avg_kill_score",
            "avg_speed",
            "avg_timing_ms",
            "avg_technique_pct",
            "hit_accuracy_pct",
        )
        invalid_values = (float("nan"), float("inf"), float("-inf"))
        for field in metric_fields:
            for invalid_value in invalid_values:
                with self.subTest(field=field, invalid_value=invalid_value):
                    with self.assertRaises(storage.CounterStrafeSessionError):
                        storage.save_counter_strafe_session(
                            **self._valid_kwargs(**{field: invalid_value})
                        )

    def test_rejects_bool_for_numeric_fields(self) -> None:
        for field in (
            "avg_kill_score",
            "avg_speed",
            "avg_timing_ms",
            "avg_technique_pct",
            "hit_accuracy_pct",
        ):
            for invalid_value in (True, False):
                with self.subTest(field=field, invalid_value=invalid_value):
                    with self.assertRaises(storage.CounterStrafeSessionError):
                        storage.save_counter_strafe_session(
                            **self._valid_kwargs(**{field: invalid_value})
                        )

    def test_rejects_float_and_bool_for_kills(self) -> None:
        for invalid_kills in (500.0, True, False):
            with self.subTest(kills=invalid_kills):
                with self.assertRaises(storage.CounterStrafeSessionError):
                    storage.save_counter_strafe_session(
                        **self._valid_kwargs(kills=invalid_kills)
                    )

    def test_drill_filter_separates_records(self) -> None:
        storage.save_counter_strafe_session(
            **self._valid_kwargs(
                session_date="2026-07-21",
                drill_name="Counter-Strafe Map",
            )
        )
        storage.save_counter_strafe_session(
            **self._valid_kwargs(
                session_date="2026-07-22",
                drill_name="Aim Lab Strafe",
            )
        )

        map_rows = storage.list_counter_strafe_sessions(
            "Jurses",
            limit=10,
            drill_name="Counter-Strafe Map",
        )
        aim_rows = storage.list_counter_strafe_sessions(
            "Jurses",
            limit=10,
            drill_name="Aim Lab Strafe",
        )
        all_rows = storage.list_counter_strafe_sessions("Jurses", limit=10)

        self.assertEqual(len(map_rows), 1)
        self.assertEqual(map_rows[0]["drill_name"], "Counter-Strafe Map")
        self.assertEqual(len(aim_rows), 1)
        self.assertEqual(aim_rows[0]["drill_name"], "Aim Lab Strafe")
        self.assertEqual(len(all_rows), 2)

    def test_rejects_invalid_limits(self) -> None:
        storage.save_counter_strafe_session(**self._valid_kwargs())
        for invalid_limit in (0, -1, 1.5, True, False):
            with self.subTest(limit=invalid_limit):
                with self.assertRaises(storage.CounterStrafeSessionError):
                    storage.list_counter_strafe_sessions("Jurses", limit=invalid_limit)


if __name__ == "__main__":
    unittest.main()
