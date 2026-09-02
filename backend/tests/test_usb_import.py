"""USB offline model manager: validate .pt/.yaml, dry-run, confirm copy+backup."""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services import model_validator as mv
from services import usb_models as usb


def _write_pt(path: Path, nc: int) -> None:
    import torch

    names = {i: f"c{i}" for i in range(max(nc, 0))}
    torch.save({"nc": nc, "names": names}, path)


class ValidatePtYamlTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        self.tmp = Path(self._tmp)

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_validate_pt_valid(self) -> None:
        p = self.tmp / "m.pt"
        _write_pt(p, 238)
        meta = mv.validate_pt_file(p)
        self.assertTrue(meta["valid"], meta)
        self.assertEqual(meta["nc"], 238)

    def test_validate_pt_invalid_nc(self) -> None:
        p = self.tmp / "bad.pt"
        _write_pt(p, 100)
        meta = mv.validate_pt_file(p)
        self.assertFalse(meta["valid"])
        self.assertIn("nc", str(meta.get("error") or ""))

    def test_validate_yaml_valid(self) -> None:
        p = self.tmp / "classes.yaml"
        p.write_text("names:\n  0: tank\n  1: truck\n", encoding="utf-8")
        meta = mv.validate_yaml_classes(p)
        self.assertTrue(meta["valid"], meta)
        self.assertEqual(meta["count"], 2)

    def test_validate_yaml_list(self) -> None:
        p = self.tmp / "list.yaml"
        p.write_text("- tank\n- truck\n- uav\n", encoding="utf-8")
        meta = mv.validate_yaml_classes(p)
        self.assertTrue(meta["valid"], meta)
        self.assertEqual(meta["count"], 3)

    def test_validate_yaml_invalid(self) -> None:
        p = self.tmp / "bad.yaml"
        p.write_text("foo: bar\n", encoding="utf-8")
        meta = mv.validate_yaml_classes(p)
        self.assertFalse(meta["valid"])


class UsbImportFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        self.tmp = Path(self._tmp)
        self.stick = self.tmp / "stick"
        self.stick.mkdir()
        self.assets = self.tmp / "assets_models"
        self.assets.mkdir()
        self.yaml_dest = self.tmp / "military_classes.yaml"
        self.yaml_dest.write_text("names:\n  0: old\n", encoding="utf-8")
        usb.set_extra_scan_roots([self.stick])
        self._orig_assets = usb.ASSETS_MODELS
        self._orig_yaml = usb.YAML_PATH
        usb.ASSETS_MODELS = self.assets
        usb.YAML_PATH = self.yaml_dest

    def tearDown(self) -> None:
        usb.set_extra_scan_roots([])
        usb.ASSETS_MODELS = self._orig_assets
        usb.YAML_PATH = self._orig_yaml
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_scan_lists_files(self) -> None:
        _write_pt(self.stick / "m.pt", 12)
        (self.stick / "classes.yaml").write_text("- a\n- b\n", encoding="utf-8")
        out = usb.scan_usb()
        self.assertTrue(out["drives"])
        names = {f["name"] for d in out["drives"] for f in d["files"]}
        self.assertIn("m.pt", names)
        self.assertIn("classes.yaml", names)

    def test_import_dry_run_does_not_copy(self) -> None:
        src = self.stick / "m.pt"
        _write_pt(src, 238)
        dest = self.assets / "yolo26n-ft.pt"
        preview = usb.preview_import(src, "model")
        self.assertTrue(preview["dry_run"])
        self.assertFalse(dest.exists())
        self.assertEqual(Path(preview["dest_path"]), dest)

    def test_import_confirm_copies_and_backups(self) -> None:
        src = self.stick / "m.pt"
        _write_pt(src, 238)
        dest = self.assets / "yolo26n-ft.pt"
        dest.write_bytes(b"OLD-WEIGHTS")
        fake_eng = mock.Mock()
        fake_eng.force_load.return_value = True
        with mock.patch("services.yolo_engine.get_yolo_engine", return_value=fake_eng), mock.patch(
            "services.db.set_setting"
        ):
            result = usb.confirm_import(src, "model")
        self.assertTrue(result["success"], result)
        self.assertTrue(dest.is_file())
        self.assertGreater(dest.stat().st_size, 20)
        backup = dest.with_name(dest.name + ".backup")
        self.assertTrue(backup.is_file())
        self.assertEqual(backup.read_bytes(), b"OLD-WEIGHTS")
        fake_eng.force_load.assert_called()

    def test_yaml_confirm_refreshes_catalog(self) -> None:
        src = self.stick / "new.yaml"
        src.write_text("names:\n  0: tank\n  1: truck\n", encoding="utf-8")
        with mock.patch.object(usb, "invalidate_class_cache") as inv, mock.patch.object(
            usb,
            "get_class_catalog",
            return_value=[{"id": 0}, {"id": 1}],
        ), mock.patch("services.response_validator.get_validator") as gv, mock.patch(
            "services.db.set_setting"
        ):
            gv.return_value.refresh_catalog = mock.Mock()
            result = usb.confirm_import(src, "classes")
        self.assertTrue(result["success"], result)
        self.assertIn("tank", self.yaml_dest.read_text(encoding="utf-8"))
        self.assertTrue((self.yaml_dest.with_name(self.yaml_dest.name + ".backup")).is_file())
        inv.assert_called()
        gv.return_value.refresh_catalog.assert_called()

    def test_rejects_path_off_usb(self) -> None:
        outsider = self.tmp / "outside.pt"
        _write_pt(outsider, 12)
        with self.assertRaises(PermissionError):
            usb.preview_import(outsider, "model")


if __name__ == "__main__":
    unittest.main()
