"""Unit tests for chunked network chat attachments."""
from __future__ import annotations

import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services import network_attachments as na


class NetworkAttachmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = Path(tempfile.mkdtemp())
        self._patch = mock.patch.object(na, "attachments_root", return_value=self._tmp)
        self._patch.start()

    def tearDown(self) -> None:
        self._patch.stop()
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _blob(self, n: int = 300_000) -> bytes:
        # Patterned payload larger than one chunk
        return bytes((i * 17) % 256 for i in range(n))

    def test_reassembly_ok(self) -> None:
        data = self._blob()
        digest = hashlib.sha256(data).hexdigest()
        meta = na.init_attachment(
            filename="shot.png",
            content_type="image/png",
            size=len(data),
            sha256=digest,
            attachment_id="aabbccddeeff0011",
        )
        cs = int(meta["chunk_size"])
        total = int(meta["total_chunks"])
        for i in range(total):
            chunk = data[i * cs : (i + 1) * cs]
            na.put_chunk(meta["id"], i, chunk)
        done = na.finalize_attachment(meta["id"])
        self.assertTrue(done["complete"])
        raw, m2 = na.read_blob(meta["id"])
        self.assertEqual(raw, data)
        self.assertEqual(m2["sha256"], digest)
        self.assertTrue(na.is_complete(meta["id"]))

    def test_sha_mismatch_reject(self) -> None:
        data = self._blob(50_000)
        wrong = hashlib.sha256(b"other").hexdigest()
        meta = na.init_attachment(
            filename="x.jpg",
            content_type="image/jpeg",
            size=len(data),
            sha256=wrong,
            attachment_id="1122334455667788",
        )
        cs = int(meta["chunk_size"])
        for i in range(int(meta["total_chunks"])):
            na.put_chunk(meta["id"], i, data[i * cs : (i + 1) * cs])
        with self.assertRaises(ValueError) as ctx:
            na.finalize_attachment(meta["id"])
        self.assertIn("sha256", str(ctx.exception).lower())
        self.assertFalse(na.is_complete(meta["id"]))

    def test_rejects_oversized(self) -> None:
        with self.assertRaises(ValueError):
            na.init_attachment(
                filename="big.bin",
                content_type="image/png",
                size=na.MAX_ATTACHMENT_BYTES + 1,
                sha256="a" * 64,
            )


if __name__ == "__main__":
    unittest.main()
