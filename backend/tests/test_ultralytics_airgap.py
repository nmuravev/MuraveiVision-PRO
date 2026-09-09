"""Air-gap: Ultralytics AutoUpdate disabled; no pip/uv from backend."""
from __future__ import annotations

import os
import unittest
from unittest import mock

from services import ultralytics_airgap as ua


class UltralyticsAirgapTests(unittest.TestCase):
    def setUp(self) -> None:
        ua._APPLIED = False
        ua._WARNED = False

    def test_apply_env_flags(self) -> None:
        os.environ.pop(ua.ENV_SKIP_CHECKS, None)
        os.environ.pop(ua.ENV_AUTOINSTALL, None)
        ua.apply_airgap_env()
        self.assertEqual(os.environ.get(ua.ENV_SKIP_CHECKS), "1")
        self.assertEqual(os.environ.get(ua.ENV_AUTOINSTALL), "0")

    def test_noop_check_requirements_no_subprocess(self) -> None:
        ua.apply_airgap_env()
        with mock.patch("subprocess.run") as run, mock.patch("subprocess.Popen") as popen:
            ua.install_check_requirements_noop()
            # Call the wrapped / noop path
            ok = ua._noop_check_requirements(["onnxruntime"])
            self.assertTrue(ok)
            run.assert_not_called()
            popen.assert_not_called()

    def test_confirmed_flag_names(self) -> None:
        # Recorded against cached ultralytics 8.4.143 source.
        self.assertEqual(ua.ENV_SKIP_CHECKS, "ULTRALYTICS_SKIP_REQUIREMENTS_CHECKS")
        self.assertEqual(ua.ENV_AUTOINSTALL, "YOLO_AUTOINSTALL")


if __name__ == "__main__":
    unittest.main()
