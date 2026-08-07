import io
import tarfile
import tempfile
import unittest
from pathlib import Path

from bootstrap.safe_extract import extract


class SafeExtractTests(unittest.TestCase):
    def test_extracts_regular_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "ok.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                info = tarfile.TarInfo("app/file.txt")
                payload = b"ok"
                info.size = len(payload)
                tar.addfile(info, io.BytesIO(payload))
            destination = root / "out"
            extract(archive, destination, max_files=10, max_bytes=100)
            self.assertEqual((destination / "app/file.txt").read_bytes(), b"ok")

    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "bad.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                info = tarfile.TarInfo("../escape.txt")
                payload = b"bad"
                info.size = len(payload)
                tar.addfile(info, io.BytesIO(payload))
            with self.assertRaises(ValueError):
                extract(archive, root / "out", max_files=10, max_bytes=100)


if __name__ == "__main__":
    unittest.main()
