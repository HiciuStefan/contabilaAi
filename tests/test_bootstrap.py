from pathlib import Path
import unittest


class BootstrapTest(unittest.TestCase):
    def test_repository_has_runtime_entrypoints(self) -> None:
        root = Path(__file__).resolve().parents[1]
        self.assertTrue((root / "app.py").exists())
        self.assertTrue((root / "requirements.txt").exists())
        self.assertTrue((root / "run-contabila.cmd").exists())


if __name__ == "__main__":
    unittest.main()
