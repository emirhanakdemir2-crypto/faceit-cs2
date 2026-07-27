from __future__ import annotations

import socket
import subprocess
import sys
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
                                    str(demo), open_browser=True, block=True, nickname="Jurses"
                                )

        self.assertEqual(code, 0)
        popen_mock.assert_called_once()
        cmd = popen_mock.call_args.args[0]
        self.assertIn("--host", cmd)
        self.assertIn("127.0.0.1", cmd)
        browser_mock.assert_called_once_with("http://127.0.0.1:3000/?nickname=Jurses")

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

    def test_select_smallest_prefers_smaller_playable_dem(self) -> None:
        demos = self.root / "data" / "demos"
        demos.mkdir(parents=True)
        large = demos / "large.dem"
        large.write_bytes(b"PBDEMS2\x00" + b"x" * 500)
        small = demos / "small.dem"
        small.write_bytes(b"PBDEMS2\x00" + b"y" * 50)
        with patch.object(replay_launcher, "repo_root", lambda: self.root):
            path, err, source = replay_launcher.select_smallest_valid_demo(demos)
        self.assertEqual(err, "")
        self.assertEqual(source, small)
        self.assertEqual(path, small.resolve())

    @patch.object(replay_launcher, "resolve_demo_path")
    def test_select_smallest_uses_playable_size_not_compressed_source(
        self,
        resolve_mock,
    ) -> None:
        demos = self.root / "data" / "demos"
        demos.mkdir(parents=True)
        small_dem = demos / "small.dem"
        small_dem.write_bytes(b"placeholder")
        tiny_zst = demos / "tiny.dem.zst"
        tiny_zst.write_bytes(b"z")
        mid_dem = demos / "mid.dem"
        mid_dem.write_bytes(b"placeholder")

        playable_small = demos / "playable_small.dem"
        playable_small.write_bytes(b"PBDEMS2\x00" + b"a" * 50)
        playable_huge = demos / "playable_huge.dem"
        playable_huge.write_bytes(b"PBDEMS2\x00" + b"b" * 5000)
        playable_mid = demos / "playable_mid.dem"
        playable_mid.write_bytes(b"PBDEMS2\x00" + b"c" * 200)

        def side_effect(raw: str) -> tuple[Path | None, str]:
            name = Path(raw).name
            if name == "small.dem":
                return playable_small, ""
            if name == "tiny.dem.zst":
                return playable_huge, ""
            if name == "mid.dem":
                return playable_mid, ""
            return None, "missing"

        resolve_mock.side_effect = side_effect
        path, err, source = replay_launcher.select_smallest_valid_demo(demos)
        self.assertEqual(err, "")
        self.assertEqual(source, small_dem)
        self.assertEqual(path, playable_small.resolve())

    @patch.object(replay_launcher, "resolve_demo_path")
    def test_select_smallest_can_pick_extracted_small_playable_from_large_zst(
        self,
        resolve_mock,
    ) -> None:
        demos = self.root / "data" / "demos"
        demos.mkdir(parents=True)
        big_zst = demos / "big.dem.zst"
        big_zst.write_bytes(b"z" * 4096)
        large_dem = demos / "large.dem"
        large_dem.write_bytes(b"placeholder")

        playable_small = demos / "extracted_small.dem"
        playable_small.write_bytes(b"PBDEMS2\x00" + b"s" * 80)
        playable_large = demos / "large_playable.dem"
        playable_large.write_bytes(b"PBDEMS2\x00" + b"l" * 900)

        def side_effect(raw: str) -> tuple[Path | None, str]:
            name = Path(raw).name
            if name == "big.dem.zst":
                return playable_small, ""
            if name == "large.dem":
                return playable_large, ""
            return None, "missing"

        resolve_mock.side_effect = side_effect
        path, err, source = replay_launcher.select_smallest_valid_demo(demos)
        self.assertEqual(err, "")
        self.assertEqual(source, big_zst)
        self.assertEqual(path, playable_small.resolve())

    @patch.object(replay_launcher, "resolve_demo_path")
    def test_select_smallest_deduplicates_dem_and_zst_for_same_playable(
        self,
        resolve_mock,
    ) -> None:
        demos = self.root / "data" / "demos"
        demos.mkdir(parents=True)
        native = demos / "match.dem"
        native.write_bytes(b"PBDEMS2\x00" + b"m" * 64)
        compressed = demos / "match.dem.zst"
        compressed.write_bytes(b"z")
        resolve_mock.side_effect = lambda raw: (native.resolve(), "")

        path, err, source = replay_launcher.select_smallest_valid_demo(demos)
        self.assertEqual(err, "")
        self.assertEqual(source, native)
        self.assertEqual(path, native.resolve())

    @patch.object(replay_launcher, "resolve_demo_path")
    def test_select_smallest_skips_broken_zst(self, resolve_mock) -> None:
        demos = self.root / "data" / "demos"
        demos.mkdir(parents=True)
        broken = demos / "broken.dem.zst"
        broken.write_bytes(b"broken")
        good = demos / "good.dem"
        good.write_bytes(b"PBDEMS2\x00" + b"g" * 32)

        def side_effect(raw: str) -> tuple[Path | None, str]:
            if Path(raw).name == "broken.dem.zst":
                return None, "Çıkarma hatası: corrupt"
            return good.resolve(), ""

        resolve_mock.side_effect = side_effect
        path, err, source = replay_launcher.select_smallest_valid_demo(demos)
        self.assertEqual(err, "")
        self.assertEqual(source, good)
        self.assertEqual(path, good.resolve())

    def test_format_demo_selection_shows_playable_and_source_sizes(self) -> None:
        demos = self.root / "data" / "demos"
        demos.mkdir(parents=True)
        source = demos / "tiny.dem.zst"
        source.write_bytes(b"z" * 10)
        playable = demos / "tiny.dem"
        playable.write_bytes(b"PBDEMS2\x00" + b"p" * 100)
        text = replay_launcher.format_demo_selection(playable, source_path=source)
        self.assertIn("Oynatılabilir boyut:", text)
        self.assertIn("Kaynak/sıkıştırılmış boyut:", text)
        self.assertIn("tiny.dem.zst", text)

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
        launch_mock.assert_called_once_with(str(demo.resolve()), nickname="Jurses")
        self.assertIn("tiny.dem", buffer.getvalue())
        self.assertIn("Oynatılabilir boyut:", buffer.getvalue())
        self.assertIn("Neden:", buffer.getvalue())

    def test_main_replay_early_exit_without_heavy_flows(self) -> None:
        demo = self.root / "match.dem"
        demo.write_bytes(b"dem")
        code, output, launch_mock = self._capture_launch(str(demo))
        self.assertEqual(code, 0)
        launch_mock.assert_called_once_with(str(demo), nickname="Jurses")
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

    def test_build_viewer_url_adds_nickname_query(self) -> None:
        url = replay_launcher.build_viewer_url("127.0.0.1", 3000, nickname="Jurses")
        self.assertEqual(url, "http://127.0.0.1:3000/?nickname=Jurses")

    def test_build_viewer_url_omits_empty_nickname(self) -> None:
        self.assertEqual(
            replay_launcher.build_viewer_url("127.0.0.1", 3001, nickname="  "),
            "http://127.0.0.1:3001/",
        )

    def test_build_viewer_url_encodes_special_characters(self) -> None:
        url = replay_launcher.build_viewer_url("127.0.0.1", 3002, nickname="Player One")
        self.assertEqual(url, "http://127.0.0.1:3002/?nickname=Player%20One")

    def test_build_viewer_url_preserves_selected_port(self) -> None:
        url = replay_launcher.build_viewer_url("127.0.0.1", 3001, nickname="Jurses")
        self.assertIn(":3001/", url)

    def test_main_replay_passes_nickname_to_launcher(self) -> None:
        demo = self.root / "match.dem"
        demo.write_bytes(b"dem")
        code, _, launch_mock = self._capture_launch(str(demo))
        self.assertEqual(code, 0)
        launch_mock.assert_called_once_with(str(demo), nickname="Jurses")

    def test_build_replay_wasm_script_exists(self) -> None:
        script = replay_launcher.repo_root() / "scripts" / "build_replay_wasm.ps1"
        self.assertTrue(script.is_file())
        content = script.read_text(encoding="utf-8")
        self.assertIn('GOOS = "js"', content)
        self.assertIn('GOARCH = "wasm"', content)
        self.assertIn("csdemoparser.wasm", content)
        self.assertIn("wasm_exec.js", content)


class ReplayArgsTests(unittest.TestCase):
    def test_parse_args_accepts_replay_demo(self) -> None:
        args = parse_args(["--nickname", "Jurses", "--replay-demo", "data/demos/x.dem"])
        self.assertEqual(args.replay_demo, "data/demos/x.dem")

    def test_parse_args_accepts_replay_demo_smallest(self) -> None:
        args = parse_args(["--nickname", "Jurses", "--replay-demo-smallest"])
        self.assertTrue(args.replay_demo_smallest)

    def test_parse_args_builds_parser_without_help_format_error(self) -> None:
        args = parse_args(["--nickname", "Jurses", "--avg-technique-pct", "42.5"])
        self.assertEqual(args.avg_technique_pct, 42.5)

    def test_main_help_shows_single_percent_sign(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "-m", "src.main", "--help"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("Counter-strafe avg technique %", result.stdout)
        self.assertIn("Counter-strafe hit accuracy %", result.stdout)
        self.assertNotIn("Counter-strafe avg technique %%", result.stdout)
        self.assertNotIn("Counter-strafe hit accuracy %%", result.stdout)
