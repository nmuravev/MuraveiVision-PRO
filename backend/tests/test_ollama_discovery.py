"""Unit tests: Ollama discovery ladder, wrong_service, startup cap, config."""
from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from services import ollama_discovery as disc
from services import ollama_proxy as proxy


class ProbeClassificationTests(unittest.TestCase):
    def test_wrong_service_non_json(self) -> None:
        with mock.patch("services.ollama_discovery.httpx.Client") as client_cls:
            client = client_cls.return_value.__enter__.return_value
            resp = mock.Mock()
            resp.status_code = 200
            resp.text = "<html>not ollama</html>"
            resp.json.side_effect = ValueError("no json")
            client.get.return_value = resp
            out = disc.probe_tags("http://127.0.0.1:11434")
            self.assertFalse(out["ok"])
            self.assertEqual(out["error_kind"], "wrong_service")
            self.assertIn("MURAVEI_OLLAMA_URL", out["message"])

    def test_wrong_service_404(self) -> None:
        with mock.patch("services.ollama_discovery.httpx.Client") as client_cls:
            client = client_cls.return_value.__enter__.return_value
            resp = mock.Mock()
            resp.status_code = 404
            resp.text = "not found"
            client.get.return_value = resp
            out = disc.probe_tags("http://127.0.0.1:11434")
            self.assertEqual(out["error_kind"], "wrong_service")

    def test_ok_tags(self) -> None:
        with mock.patch("services.ollama_discovery.httpx.Client") as client_cls:
            client = client_cls.return_value.__enter__.return_value
            resp = mock.Mock()
            resp.status_code = 200
            resp.json.return_value = {"models": [{"name": "qwen2.5vl:7b", "size": 1e9}]}
            client.get.return_value = resp
            out = disc.probe_tags("http://127.0.0.1:11434")
            self.assertTrue(out["ok"])
            self.assertEqual(len(out["models"]), 1)


class LadderOrderTests(unittest.TestCase):
    def test_env_wins(self) -> None:
        with mock.patch.dict("os.environ", {"MURAVEI_OLLAMA_URL": "http://10.0.0.9:11434"}):
            with mock.patch.object(disc, "_inside_wsl", return_value=False):
                with mock.patch.object(disc, "_windows_wsl_instance_candidates", return_value=[]):
                    cands = disc.ladder_candidates(saved_base="http://192.168.1.5:11434")
        self.assertEqual(cands[0], "http://10.0.0.9:11434")
        self.assertIn("http://127.0.0.1:11434", cands)
        self.assertIn("http://192.168.1.5:11434", cands)

    def test_discover_skips_dead_continues(self) -> None:
        calls: list[str] = []

        def fake_probe(base: str, *, timeout: float = 5.0) -> dict:
            calls.append(base)
            if "10.0.0.9" in base:
                return {
                    "ok": False,
                    "base_url": base,
                    "models": [],
                    "error_kind": "wrong_service",
                    "message": disc.MSG_WRONG_SERVICE,
                    "elapsed_ms": 1,
                }
            if "127.0.0.1" in base:
                return {
                    "ok": True,
                    "base_url": base,
                    "models": [{"name": "m"}],
                    "error_kind": "",
                    "message": "",
                    "elapsed_ms": 1,
                }
            return {
                "ok": False,
                "base_url": base,
                "models": [],
                "error_kind": "refused",
                "message": disc.MSG_REFUSED,
                "elapsed_ms": 1,
            }

        with mock.patch.dict("os.environ", {"MURAVEI_OLLAMA_URL": "http://10.0.0.9:11434"}):
            with mock.patch.object(disc, "probe_tags", side_effect=fake_probe):
                with mock.patch.object(disc, "_inside_wsl", return_value=False):
                    with mock.patch.object(disc, "_windows_wsl_instance_candidates", return_value=[]):
                        out = disc.discover_first_healthy()
        self.assertTrue(out["ok"])
        self.assertIn("127.0.0.1", out["base_url"])
        self.assertEqual(calls[0], "http://10.0.0.9:11434")

    def test_startup_deadline_aborts(self) -> None:
        def slow_probe(base: str, *, timeout: float = 5.0) -> dict:
            time.sleep(0.2)
            return {
                "ok": False,
                "base_url": base,
                "models": [],
                "error_kind": "refused",
                "message": disc.MSG_REFUSED,
                "elapsed_ms": 200,
            }

        deadline = time.monotonic() + 0.35
        with mock.patch.object(disc, "probe_tags", side_effect=slow_probe):
            with mock.patch.object(disc, "ladder_candidates", return_value=[
                "http://a:11434",
                "http://b:11434",
                "http://c:11434",
                "http://d:11434",
            ]):
                out = disc.discover_first_healthy(deadline=deadline, per_probe_timeout=5.0)
        self.assertFalse(out["ok"])
        # Should not have tried all four under 0.35s with 0.2s each
        self.assertLessEqual(len(out.get("tried") or []), 3)


class LanScanCapTests(unittest.TestCase):
    def test_wall_clock(self) -> None:
        net = __import__("ipaddress").IPv4Network("10.0.0.0/24", strict=False)

        def fake_nets():
            return [net]

        with mock.patch.object(disc, "_local_ipv4_networks", side_effect=fake_nets):
            with mock.patch.object(disc, "_tcp_open", return_value=False):
                t0 = time.perf_counter()
                rows = disc.scan_lan_ollama(wall_sec=0.5, tcp_timeout=0.05)
                elapsed = time.perf_counter() - t0
        self.assertLess(elapsed, 2.0)
        self.assertEqual(rows, [])


class ProxyManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        proxy.reset_for_tests()
        self._tmp = tempfile.TemporaryDirectory()
        self.cfg_dir = Path(self._tmp.name) / "config" / "local"
        self.cfg_dir.mkdir(parents=True)
        self.cfg_path = self.cfg_dir / "ollama.json"
        self._patchers = [
            mock.patch.object(proxy, "CONFIG_DIR", self.cfg_dir),
            mock.patch.object(proxy, "CONFIG_PATH", self.cfg_path),
            mock.patch.object(proxy, "BASE_DIR", Path(self._tmp.name)),
        ]
        for p in self._patchers:
            p.start()

    def tearDown(self) -> None:
        proxy.reset_for_tests()
        for p in self._patchers:
            p.stop()
        self._tmp.cleanup()

    def test_config_roundtrip(self) -> None:
        proxy.save_config(
            {
                "base_url": "http://10.1.2.3:11434",
                "host": "10.1.2.3",
                "port": 11434,
                "model": "qwen2.5vl:7b",
                "timeout_sec": 45,
                "auto_reconnect": True,
                "last_ok_at": "",
            }
        )
        loaded = proxy.load_config()
        self.assertEqual(loaded["host"], "10.1.2.3")
        self.assertEqual(loaded["model"], "qwen2.5vl:7b")
        self.assertTrue(self.cfg_path.is_file())
        raw = json.loads(self.cfg_path.read_text(encoding="utf-8"))
        self.assertEqual(raw["base_url"], "http://10.1.2.3:11434")

    def test_list_models_calm_when_disconnected(self) -> None:
        st = proxy.list_models()
        self.assertFalse(st["available"])
        self.assertEqual(st["state"], "disconnected")

    def test_connect_forced_ok(self) -> None:
        with mock.patch.object(
            proxy,
            "probe_tags",
            return_value={
                "ok": True,
                "base_url": "http://127.0.0.1:11434",
                "models": [{"name": "x:latest", "size": 100}],
                "error_kind": "",
                "message": "",
            },
        ):
            st = proxy.connect(base_url="http://127.0.0.1:11434")
        self.assertEqual(st["state"], "connected")
        self.assertTrue(st["available"])

    def test_startup_reconnect_non_blocking(self) -> None:
        proxy.save_config(
            {
                "base_url": "http://127.0.0.1:11434",
                "host": "127.0.0.1",
                "port": 11434,
                "model": "",
                "timeout_sec": 60,
                "auto_reconnect": True,
                "last_ok_at": "",
            }
        )

        def slow_discover(**_kwargs):
            time.sleep(0.25)
            return {"ok": False, "message": "fail", "error_kind": "refused", "models": []}

        with mock.patch.object(proxy, "discover_first_healthy", side_effect=slow_discover):
            t0 = time.perf_counter()
            proxy.startup_reconnect()
            elapsed = time.perf_counter() - t0
            self.assertLess(elapsed, 0.15)
            deadline = time.time() + 2.0
            while time.time() < deadline:
                if proxy.get_status()["state"] == "disconnected":
                    break
                time.sleep(0.05)
            self.assertEqual(proxy.get_status()["state"], "disconnected")


if __name__ == "__main__":
    unittest.main()
