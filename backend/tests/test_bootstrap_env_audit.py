"""Unit tests for portable venv audit / fingerprint (Z2)."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services import portable_bootstrap as pb


class PortableEnvAuditTests(unittest.TestCase):
    def tearDown(self) -> None:
        for k in (
            "MURAVEI_BUILD_PROFILE",
            "MURAVEI_BOOTSTRAP_ONLINE",
            "MURAVEI_WHEELS_DIR",
            "MURAVEI_FORCE_ACCELERATOR",
        ):
            os.environ.pop(k, None)

    def test_parse_req_names(self) -> None:
        names = pb._parse_req_names("fastapi>=1\n# c\nnumpy>=1.26.0,<2\nuvicorn[standard]>=0.24\n")
        self.assertIn("fastapi", names)
        self.assertIn("numpy", names)
        self.assertIn("uvicorn", names)

    def test_requirements_hash_stable(self) -> None:
        h1 = pb.requirements_hash()
        h2 = pb.requirements_hash()
        self.assertTrue(len(h1) == 64)
        self.assertEqual(h1, h2)

    def test_fingerprint_includes_requirements_hash(self) -> None:
        fp = pb.compute_fingerprint(build_profile="mini")
        self.assertEqual(fp["requirements_sha256"], pb.requirements_hash())
        self.assertEqual(fp["build_profile"], "mini")
        self.assertIn(fp["torch_variant"], ("cuda", "cpu", "none"))

    def test_stamp_mismatch_on_requirements_change(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            stamp = Path(td) / "bootstrap_complete.json"
            stamp.write_text(
                json.dumps(
                    {
                        "build_profile": "mini",
                        "fingerprint": {
                            "requirements_sha256": "0" * 64,
                            "torch_variant": "cpu",
                            "gpu_present": False,
                            "build_profile": "mini",
                        },
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(pb, "_STAMP", stamp):
                with mock.patch.object(
                    pb,
                    "compute_fingerprint",
                    return_value={
                        "requirements_sha256": "1" * 64,
                        "torch_variant": "cpu",
                        "gpu_present": False,
                        "build_profile": "mini",
                    },
                ):
                    self.assertFalse(pb.stamp_matches())

    def test_env_absent(self) -> None:
        with mock.patch.object(pb, "venv_python", return_value=None):
            self.assertEqual(pb.env_status(), "absent")
            audit = pb.audit_env("mini")
            self.assertTrue(audit["needs_full_rebuild"])

    def test_env_broken_dead_interpreter(self) -> None:
        fake = Path("muravei_env/Scripts/python.exe")
        with mock.patch.object(pb, "venv_python", return_value=fake):
            with mock.patch.object(pb, "interpreter_alive", return_value=False):
                self.assertEqual(pb.env_status(), "broken")
                audit = pb.audit_env("full")
                self.assertTrue(audit["needs_full_rebuild"])

    def test_env_broken_bad_pyvenv_cfg(self) -> None:
        fake = Path("muravei_env/Scripts/python.exe")
        with mock.patch.object(pb, "venv_python", return_value=fake):
            with mock.patch.object(pb, "interpreter_alive", return_value=True):
                with mock.patch.object(pb, "pyvenv_cfg_valid", return_value=False):
                    self.assertEqual(pb.env_status(), "broken")

    def test_incomplete_packages(self) -> None:
        fake = Path("muravei_env/Scripts/python.exe")
        with mock.patch.object(pb, "venv_python", return_value=fake):
            with mock.patch.object(pb, "interpreter_alive", return_value=True):
                with mock.patch.object(pb, "pyvenv_cfg_valid", return_value=True):
                    with mock.patch.object(pb, "missing_packages", return_value=["fastapi", "torch"]):
                        with mock.patch.object(pb, "torch_variant", return_value={"installed": False}):
                            audit = pb.audit_env("mini")
                            self.assertEqual(audit["env_status"], "alive")
                            self.assertIn("fastapi", audit["missing_packages"])

    def test_verify_sha256_reject(self) -> None:
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"abc")
            path = Path(f.name)
        try:
            self.assertFalse(pb.verify_sha256(path, "0" * 64))
            digest = pb.sha256_file(path)
            self.assertTrue(pb.verify_sha256(path, digest))
        finally:
            path.unlink(missing_ok=True)

    def test_heal_calls_install_when_missing(self) -> None:
        fake = Path("muravei_env/Scripts/python.exe")
        with mock.patch.object(pb, "venv_python", return_value=fake):
            with mock.patch.object(pb, "interpreter_alive", return_value=True):
                with mock.patch.object(pb, "missing_packages", side_effect=[["fastapi"], []]):
                    with mock.patch.object(
                        pb,
                        "install_requirements_offline_first",
                        return_value={"ok": True, "mode": "offline_wheels"},
                    ) as inst:
                        with mock.patch.object(
                            pb,
                            "reconcile_torch",
                            return_value={"ok": True, "messages": [], "action": "noop"},
                        ):
                            out = pb.heal_env("mini")
                            self.assertTrue(out["ok"])
                            inst.assert_called_once()


if __name__ == "__main__":
    unittest.main()
