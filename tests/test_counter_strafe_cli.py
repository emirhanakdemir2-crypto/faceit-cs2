from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from src import counter_strafe_cli, storage
from src.main import main, parse_args

VALID_LOG_ARGS = [
    "--nickname",
    "Jurses",
    "--log-counter-strafe",
    "--session-date",
    "2026-07-23",
    "--drill-name",
    "MAP_ADI",
    "--kills",
    "500",
    "--avg-kill-score",
    "69.2",
    "--avg-speed",
    "14.3",
    "--avg-timing-ms",
    "207",
    "--avg-technique-pct",
    "50.8",
    "--hit-accuracy-pct",
    "51.5",
]

CONFLICTING_FLAG_CASES = [
    (["--matches", "10"], "--matches"),
    (["--days", "30"], "--days"),
    (["--recent", "5"], "--recent"),
    (["--post-session"], "--post-session"),
    (["--ai"], "--ai"),
    (["--export-ai-prompt"], "--export-ai-prompt"),
    (["--demo-folder", "data/demos"], "--demo-folder"),
    (["--mechanics"], "--mechanics"),
    (["--debug-demo"], "--debug-demo"),
    (["--tara"], "--tara"),
    (["--suite"], "--suite"),
]


class CounterStrafeCliTestCase(unittest.TestCase):
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

    def _run_main(self, argv: list[str]) -> int:
        with patch("src.main.get_api_key", side_effect=AssertionError("FACEIT API must not run")):
            with patch(
                "src.main.collect_player_data",
                side_effect=AssertionError("collect_player_data must not run"),
            ):
                return main(argv)

    def _run_main_capture(self, argv: list[str]) -> tuple[int, str]:
        buffer = StringIO()
        test_console = counter_strafe_cli.console.__class__(file=buffer, force_terminal=True)
        with patch.object(counter_strafe_cli, "console", test_console):
            code = self._run_main(argv)
        return code, buffer.getvalue()


class CounterStrafeCliTests(CounterStrafeCliTestCase):
    def test_successful_log_exit_zero(self) -> None:
        code = self._run_main(VALID_LOG_ARGS)
        self.assertEqual(code, 0)
        rows = storage.list_counter_strafe_sessions("Jurses", limit=1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["kills"], 500)

    def test_success_output_contains_id_and_metrics(self) -> None:
        code, output = self._run_main_capture(VALID_LOG_ARGS)
        self.assertEqual(code, 0)
        for token in (
            "Kayıt ID",
            "2026-07-23",
            "MAP_ADI",
            "500",
            "69.2",
            "14.3",
            "207",
            "50.8",
            "51.5",
        ):
            self.assertIn(token, output)

    def test_missing_multiple_fields_single_message(self) -> None:
        with patch.object(counter_strafe_cli, "init_db") as init_db_mock:
            with patch.object(counter_strafe_cli, "save_counter_strafe_session") as save_mock:
                code, output = self._run_main_capture(
                    ["--nickname", "Jurses", "--log-counter-strafe"]
                )
        self.assertEqual(code, 1)
        self.assertIn("eksik zorunlu alanlar", output.lower())
        for flag in (
            "--session-date",
            "--drill-name",
            "--kills",
            "--avg-kill-score",
            "--avg-speed",
            "--avg-timing-ms",
            "--avg-technique-pct",
            "--hit-accuracy-pct",
        ):
            self.assertIn(flag, output)
        init_db_mock.assert_not_called()
        save_mock.assert_not_called()

    def test_invalid_date_exit_one_no_save(self) -> None:
        argv = list(VALID_LOG_ARGS)
        idx = argv.index("--session-date")
        argv[idx + 1] = "2026-02-30"
        code = self._run_main(argv)
        self.assertEqual(code, 1)
        storage.init_db()
        rows = storage.list_counter_strafe_sessions("Jurses", limit=10)
        self.assertEqual(len(rows), 0)

    def test_invalid_numeric_exit_one(self) -> None:
        argv = list(VALID_LOG_ARGS)
        idx = argv.index("--avg-timing-ms")
        argv[idx + 1] = "-1"
        code = self._run_main(argv)
        self.assertEqual(code, 1)
        self.assertEqual(len(storage.list_counter_strafe_sessions("Jurses", limit=10)), 0)

    def test_storage_error_exit_one(self) -> None:
        with patch.object(
            counter_strafe_cli,
            "save_counter_strafe_session",
            side_effect=storage.CounterStrafeSessionError("db failure"),
        ):
            code = self._run_main(VALID_LOG_ARGS)
        self.assertEqual(code, 1)

    def test_orphan_log_field_blocks_normal_flow(self) -> None:
        code, output = self._run_main_capture(
            ["--nickname", "Jurses", "--session-date", "2026-07-23"]
        )
        self.assertEqual(code, 1)
        self.assertIn("--log-counter-strafe", output)

    def test_valid_evidence_path_accepted(self) -> None:
        evidence = Path(self._tmpdir.name) / "proof.png"
        evidence.write_bytes(b"fake")
        argv = VALID_LOG_ARGS + ["--evidence-path", str(evidence)]
        code = self._run_main(argv)
        self.assertEqual(code, 0)
        rows = storage.list_counter_strafe_sessions("Jurses", limit=1)
        self.assertEqual(rows[0]["evidence_path"], str(evidence))

    def test_missing_evidence_path_rejected(self) -> None:
        argv = VALID_LOG_ARGS + ["--evidence-path", str(Path(self._tmpdir.name) / "missing.png")]
        code = self._run_main(argv)
        self.assertEqual(code, 1)

    def test_directory_evidence_path_rejected(self) -> None:
        evidence_dir = Path(self._tmpdir.name) / "proof_dir"
        evidence_dir.mkdir()
        argv = VALID_LOG_ARGS + ["--evidence-path", str(evidence_dir)]
        code = self._run_main(argv)
        self.assertEqual(code, 1)

    def test_argparse_type_error_keeps_exit_code_two(self) -> None:
        argv = ["--nickname", "Jurses", "--log-counter-strafe", "--kills", "not-int"]
        with patch.object(sys, "argv", ["src.main", *argv]):
            with patch.object(sys, "stderr", new_callable=StringIO):
                with self.assertRaises(SystemExit) as ctx:
                    parse_args(argv)
        self.assertEqual(ctx.exception.code, 2)

    def test_heavy_flows_not_called_on_success(self) -> None:
        with patch("src.main.get_api_key", side_effect=AssertionError("API")) as api_mock:
            with patch(
                "src.main.collect_player_data",
                side_effect=AssertionError("collect"),
            ) as collect_mock:
                with patch(
                    "src.main.run_mechanics_lab",
                    create=True,
                    side_effect=AssertionError("mechanics"),
                ):
                    code = main(VALID_LOG_ARGS)
        self.assertEqual(code, 0)
        api_mock.assert_not_called()
        collect_mock.assert_not_called()


class CounterStrafeConflictTests(CounterStrafeCliTestCase):
    def test_log_mode_with_each_conflicting_flag(self) -> None:
        for extra_args, flag in CONFLICTING_FLAG_CASES:
            with self.subTest(flag=flag):
                with patch.object(counter_strafe_cli, "init_db") as init_db_mock:
                    with patch.object(
                        counter_strafe_cli,
                        "save_counter_strafe_session",
                    ) as save_mock:
                        code, output = self._run_main_capture(VALID_LOG_ARGS + extra_args)
                self.assertEqual(code, 1, msg=flag)
                self.assertIn(flag, output)
                init_db_mock.assert_not_called()
                save_mock.assert_not_called()


class CounterStrafeCliUnitTests(unittest.TestCase):
    def test_find_missing_required_log_fields(self) -> None:
        args = parse_args(["--nickname", "Jurses", "--log-counter-strafe"])
        missing = counter_strafe_cli.find_missing_required_log_fields(args)
        self.assertEqual(len(missing), 8)

    def test_find_orphan_log_fields(self) -> None:
        args = parse_args(["--nickname", "Jurses", "--kills", "500"])
        orphans = counter_strafe_cli.find_orphan_log_fields(args)
        self.assertIn("--kills", orphans)


if __name__ == "__main__":
    unittest.main()
