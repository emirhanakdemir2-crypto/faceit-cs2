from __future__ import annotations

import socket
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from src import replay_launcher
from src.main import main, parse_args


class ReplayLauncherTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self.web = self.root / replay_launcher.VIEWER_WEB_REL
        self.wasm = self.web / "public" / "wasm"
        self.web.mkdir(parents=True)
        self.wasm.mkdir(parents=True)
        (self.web / "package.json").write_text("{}", encoding="utf-8")
        (self.web / "node_modules").mkdir()
        for name in replay_launcher.WASM_FILES:
            (self.wasm / name).write_bytes(b"x")

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _patch_viewer_paths(self):
        return patch.multiple(
            replay_launcher,
            repo_root=lambda: self.root,
            viewer_web_dir=lambda: self.web,
            wasm_dir=lambda: self.wasm,
        )

    def _run_main(self, argv: list[str]) -> int:
        with patch("src.main.get_api_key", side_effect=AssertionError("FACEIT API must not run")):
            with patch(
                "src.main.collect_player_data",
                side_effect=AssertionError("collect_player_data must not run"),
            ):
                with patch("src.main.init_db", side_effect=AssertionError("init_db must not run")):
                    return main(argv)

    def _capture_launch(self, demo: str, **kwargs):
        buffer = StringIO()
        test_console = replay_launcher.console.__class__(file=buffer, force_terminal=True)
        with self._patch_viewer_paths():
            with patch.object(replay_launcher, "console", test_console):
                with patch("src.main.launch_replay_demo") as launch_mock:
                    launch_mock.return_value = 0
                    code = self._run_main(["--nickname", "Jurses", "--replay-demo", demo])
        return code, buffer.getvalue(), launch_mock


class ReplayLauncherTests(ReplayLauncherTestCase):
    def test_resolve_valid_dem(self) -> None:
        demo = self.root / "match.dem"
        demo.write_bytes(b"dem")
        with patch.object(replay_launcher, "repo_root", lambda: self.root):
            path, err = replay_launcher.resolve_demo_path(str(demo))
        self.assertEqual(err, "")
        self.assertEqual(path, demo.resolve())

    def test_resolve_missing_file(self) -> None:
        path, err = replay_launcher.resolve_demo_path(str(self.root / "missing.dem"))
        self.assertIsNone(path)
        self.assertIn("bulunamadı", err)

    def test_resolve_invalid_extension(self) -> None:
        bad = self.root / "notes.txt"
        bad.write_text("x", encoding="utf-8")
        path, err = replay_launcher.resolve_demo_path(str(bad))
        self.assertIsNone(path)
        self.assertIn("Geçersiz demo uzantısı", err)

    def test_viewer_missing_submodule(self) -> None:
        empty = self.root / "empty"
        empty.mkdir()
        with patch.object(replay_launcher, "repo_root", lambda: empty):
            with patch.object(replay_launcher, "viewer_web_dir", lambda: empty / "missing"):
                ready, msg = replay_launcher.check_viewer_ready()
        self.assertFalse(ready)
        self.assertIn("CS2 2D demo viewer hazır değil", msg)

    def test_viewer_missing_wasm(self) -> None:
        (self.wasm / "csdemoparser.wasm").unlink()
        with self._patch_viewer_paths():
            ready, msg = replay_launcher.check_viewer_ready()
        self.assertFalse(ready)
        self.assertIn("Eksik WASM dosyaları", msg)

    def test_build_vite_command_binds_localhost(self) -> None:
        with patch("shutil.which", return_value="npm"):
            cmd = replay_launcher.build_vite_command(3001, "127.0.0.1")
        self.assertEqual(cmd[-4:], ["--host", "127.0.0.1", "--port", "3001"])

    def test_launch_server_start_failure(self) -> None:
        demo = self.root / "match.dem"
        demo.write_bytes(b"dem")
        with self._patch_viewer_paths():
            with patch("shutil.which", return_value="npm"):
                with patch("src.replay_launcher.subprocess.Popen", side_effect=OSError("boom")):
                    code = replay_launcher.launch_replay_demo(
                        str(demo), open_browser=False, block=False
                    )
        self.assertEqual(code, 1)

    def test_launch_success_mocks_subprocess_and_browser(self) -> None:
        demo = self.root / "match.dem"
        demo.write_bytes(b"dem")
        proc = MagicMock()
        proc.wait.return_value = 0

        with self._patch_viewer_paths():
            with patch("shutil.which", return_value="npm"):
                with patch("src.replay_launcher.pick_port", return_value=3000):
                    with patch("src.replay_launcher.subprocess.Popen", return_value=proc) as popen_mock:
                        with patch("src.replay_launcher.wait_for_server", return_value=True):
                            with patch("src.replay_launcher.webbrowser.open") as browser_mock:
                                code = replay_launcher.launch_replay_demo(
                                    str(demo), open_browser=True, block=True
                                )

        self.assertEqual(code, 0)
        popen_mock.assert_called_once()
        cmd = popen_mock.call_args.args[0]
        self.assertIn("--host", cmd)
        self.assertIn("127.0.0.1", cmd)
        browser_mock.assert_called_once_with("http://127.0.0.1:3000/")

    def test_select_smallest_valid_demo_skips_invalid_header(self) -> None:
        demos = self.root / "data" / "demos"
        demos.mkdir(parents=True)
        bad = demos / "bad.dem"
        bad.write_bytes(b"NOTDEMO")
        good = demos / "good.dem"
        good.write_bytes(b"PBDEMS2\x00" + b"x" * 32)
        with patch.object(replay_launcher, "repo_root", lambda: self.root):
            path, err, source = replay_launcher.select_smallest_valid_demo(demos)
        self.assertEqual(err, "")
        self.assertEqual(source, good)
        self.assertEqual(path, good.resolve())

    def test_select_smallest_valid_demo_tries_next_candidate(self) -> None:
        demos = self.root / "data" / "demos"
        demos.mkdir(parents=True)
        empty = demos / "empty.dem"
        empty.write_bytes(b"")
        good = demos / "tiny.dem"
        good.write_bytes(b"PBDEMS2\x00" + b"y" * 16)
        with patch.object(replay_launcher, "repo_root", lambda: self.root):
            path, err, source = replay_launcher.select_smallest_valid_demo(demos)
        self.assertEqual(err, "")
        self.assertEqual(source, good)
        self.assertEqual(path, good.resolve())

    def test_main_replay_demo_smallest_launches_selected_file(self) -> None:
        demos = self.root / "data" / "demos"
        demos.mkdir(parents=True)
        demo = demos / "tiny.dem"
        demo.write_bytes(b"PBDEMS2\x00" + b"z" * 12)
        buffer = StringIO()
        test_console = replay_launcher.console.__class__(file=buffer, force_terminal=True)
        with self._patch_viewer_paths():
            with patch.object(replay_launcher, "repo_root", lambda: self.root):
                with patch("src.main.console", test_console):
                    with patch("src.main.launch_replay_demo") as launch_mock:
                        launch_mock.return_value = 0
                        code = self._run_main(
                            ["--nickname", "Jurses", "--replay-demo-smallest"]
                        )
        self.assertEqual(code, 0)
        launch_mock.assert_called_once_with(str(demo.resolve()))
        self.assertIn("tiny.dem", buffer.getvalue())
        self.assertIn("Neden:", buffer.getvalue())

    def test_main_replay_early_exit_without_heavy_flows(self) -> None:
        demo = self.root / "match.dem"
        demo.write_bytes(b"dem")
        code, output, launch_mock = self._capture_launch(str(demo))
        self.assertEqual(code, 0)
        launch_mock.assert_called_once_with(str(demo))
        self.assertNotIn("FACEIT CS2 Koçluk", output)

    def test_main_replay_conflict_with_analysis_flags(self) -> None:
        code = self._run_main(
            ["--nickname", "Jurses", "--replay-demo", "a.dem", "--suite"]
        )
        self.assertEqual(code, 1)

    def test_pick_port_only_on_localhost(self) -> None:
        port = replay_launcher.pick_port("127.0.0.1")
        self.assertIsNotNone(port)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", port))
            with self.assertRaises(OSError):
                sock.bind(("0.0.0.0", port))


class ReplayArgsTests(unittest.TestCase):
    def test_parse_args_accepts_replay_demo(self) -> None:
        args = parse_args(["--nickname", "Jurses", "--replay-demo", "data/demos/x.dem"])
        self.assertEqual(args.replay_demo, "data/demos/x.dem")

    def test_parse_args_accepts_replay_demo_smallest(self) -> None:
        args = parse_args(["--nickname", "Jurses", "--replay-demo-smallest"])
        self.assertTrue(args.replay_demo_smallest)
