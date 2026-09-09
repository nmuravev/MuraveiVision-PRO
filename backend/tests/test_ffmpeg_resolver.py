"""ffmpeg resolver order: MURAVEI_FFMPEG_DIR → pack → sidecars → PATH."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services import ffmpeg_util as fu


class FfmpegResolverOrderTests(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ.pop("MURAVEI_FFMPEG_DIR", None)

    def _touch(self, d: Path, name: str) -> Path:
        d.mkdir(parents=True, exist_ok=True)
        p = d / name
        p.write_bytes(b"x")
        return p

    def test_env_wins_over_pack(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            env_dir = root / "env"
            pack = root / "assets" / "ffmpeg"
            self._touch(env_dir, "ffmpeg.exe")
            self._touch(pack, "ffmpeg.exe")
            os.environ["MURAVEI_FFMPEG_DIR"] = str(env_dir)
            with mock.patch.object(fu, "BASE_DIR", root):
                path, src = fu.resolve_ffmpeg()
            self.assertEqual(src, "env")
            self.assertTrue(path and path.endswith("ffmpeg.exe"))
            self.assertIn(str(env_dir), path.replace("/", "\\") if False else path)

    def test_pack_wins_over_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pack = root / "assets" / "ffmpeg"
            side = root / "sidecars" / "ffmpeg"
            self._touch(pack, "ffmpeg.exe")
            self._touch(side, "ffmpeg.exe")
            with mock.patch.object(fu, "BASE_DIR", root), mock.patch(
                "shutil.which", return_value=str(root / "path" / "ffmpeg.exe")
            ):
                path, src = fu.resolve_ffmpeg()
            self.assertEqual(src, "pack")
            self.assertIn("assets", path.replace("\\", "/"))

    def test_sidecar_wins_over_path(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            side = root / "sidecars" / "ffmpeg"
            self._touch(side, "ffmpeg.exe")
            with mock.patch.object(fu, "BASE_DIR", root), mock.patch(
                "shutil.which", return_value=str(root / "sys" / "ffmpeg.exe")
            ):
                path, src = fu.resolve_ffmpeg()
            self.assertEqual(src, "sidecar")

    def test_path_when_pack_absent(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fake = str(root / "sys" / "ffmpeg.exe")
            with mock.patch.object(fu, "BASE_DIR", root), mock.patch(
                "shutil.which", return_value=fake
            ):
                path, src = fu.resolve_ffmpeg()
            self.assertEqual(src, "path")
            self.assertEqual(path, fake)

    def test_ffprobe_same_order(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pack = root / "assets" / "ffmpeg"
            self._touch(pack, "ffprobe.exe")
            with mock.patch.object(fu, "BASE_DIR", root), mock.patch(
                "shutil.which", return_value=str(root / "sys" / "ffprobe.exe")
            ):
                path, src = fu.resolve_ffprobe()
            self.assertEqual(src, "pack")
            self.assertTrue(path and "ffprobe" in path)


if __name__ == "__main__":
    unittest.main()
