"""Unit tests for recon package share (chunk + disk preflight + resume)."""
from __future__ import annotations

import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services import network_recon_share as nr


class ReconPackageShareTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = Path(tempfile.mkdtemp())
        self._recon = self._tmp / "recon"
        self._pkgs = self._tmp / "pkgs"
        self._recon.mkdir()
        self._pkgs.mkdir()
        self._patches = [
            mock.patch.object(nr, "recon_root", return_value=self._recon),
            mock.patch.object(nr, "packages_root", return_value=self._pkgs),
            mock.patch.object(nr, "BASE_DIR", self._tmp),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self) -> None:
        for p in self._patches:
            p.stop()
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _make_job(self, job_id: str = "aabbccddee01") -> Path:
        job = self._recon / job_id
        job.mkdir()
        dense = job / "dense.ply"
        dense.write_bytes(bytes((i * 3) % 256 for i in range(300_000)))
        (job / "manifest.json").write_text(
            '{"status":"done","artifacts":{"dense":{"file":"dense.ply"}}}',
            encoding="utf-8",
        )
        return job

    def test_offer_and_unpack(self) -> None:
        self._make_job()
        man = nr.create_offer(job_id="aabbccddee01", kinds=["dense"], source_base="Hub")
        self.assertTrue(man["complete"])
        self.assertIn("dense", man["artifacts"])
        # Simulate receive on another tree: re-init then chunks from offer blob
        offer = man
        pid = offer["id"]
        # Fresh receive dir — wipe package and re-accept
        shutil.rmtree(self._pkgs / pid, ignore_errors=True)
        arts = offer["artifacts"]
        # Drop complete flags for receive
        recv_arts = {
            k: {
                **v,
                "complete": False,
                "staged": False,
            }
            for k, v in arts.items()
        }
        # Restore offer blobs for read_chunk by recreating offer first
        man2 = nr.create_offer(
            job_id="aabbccddee01",
            kinds=["dense"],
            package_id="bbccddeeff001122",
            source_base="Hub",
        )
        pid2 = man2["id"]
        # Receive into new id by copying meta without blobs
        shutil.rmtree(self._pkgs / "ccdd001122334455", ignore_errors=True)
        recv = nr.init_receive(
            package_id="ccdd001122334455",
            job_id="aabbccddee01",
            artifacts=man2["artifacts"],
            selected=["dense"],
        )
        art = man2["artifacts"]["dense"]
        total = int(art["total_chunks"])
        for i in range(total):
            raw = nr.read_chunk_bytes(pid2, "dense", i)
            nr.put_chunk(recv["id"], "dense", i, raw)
        nr.finalize_artifact(recv["id"], "dense")
        # Unpack to new job folder
        job2 = self._recon / "aabbccddee01"
        if job2.exists():
            shutil.rmtree(job2)
        out = nr.unpack_to_recon(recv["id"])
        self.assertEqual(out["job_id"], "aabbccddee01")
        self.assertTrue((self._recon / "aabbccddee01" / "dense.ply").is_file())

    def test_disk_preflight_reject(self) -> None:
        with mock.patch.object(nr, "free_bytes", return_value=100):
            pre = nr.disk_preflight(10_000)
            self.assertFalse(pre["ok"])
            self.assertIn("Недостаточно", pre["message"] or "")

    def test_sha_mismatch_and_resume(self) -> None:
        job = self._make_job()
        # Ensure >1 chunk
        dense = job / "dense.ply"
        dense.write_bytes(bytes((i * 3) % 256 for i in range(nr.CHUNK_SIZE + 50_000)))
        man = nr.create_offer(job_id="aabbccddee01", kinds=["dense"], package_id="ddeeff0011223344")
        pid = man["id"]
        art = man["artifacts"]["dense"]
        total = int(art["total_chunks"])
        self.assertGreaterEqual(total, 2)
        recv_id = "eeff001122334455"
        bad_arts = {
            "dense": {
                **{k: v for k, v in art.items() if k != "complete"},
                "complete": False,
                "sha256": hashlib.sha256(b"wrong").hexdigest(),
            }
        }
        nr.init_receive(
            package_id=recv_id,
            job_id="aabbccddee01",
            artifacts=bad_arts,
            selected=["dense"],
        )
        # Upload only first chunk — resume should report next=1
        nr.put_chunk(recv_id, "dense", 0, nr.read_chunk_bytes(pid, "dense", 0))
        nxt = nr.next_missing_chunk(recv_id, "dense")
        self.assertEqual(nxt, 1)
        for i in range(1, total):
            nr.put_chunk(recv_id, "dense", i, nr.read_chunk_bytes(pid, "dense", i))
        with self.assertRaises(ValueError) as ctx:
            nr.finalize_artifact(recv_id, "dense")
        self.assertIn("sha256", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
