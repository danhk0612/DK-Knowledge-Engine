"""T23: Builder dependency license collection from installed wheels."""
import tempfile
import unittest
from pathlib import Path

from importlib.util import module_from_spec, spec_from_file_location

MODULE_PATH = Path(__file__).resolve().parents[1] / "distribution" / "collect-builder-licenses.py"
spec = spec_from_file_location("builder_licenses", MODULE_PATH)
module = module_from_spec(spec)
spec.loader.exec_module(module)


class BuilderLicenseTests(unittest.TestCase):
    def test_required_license_texts_are_copied(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "licenses"
            result = module.collect(output)
            self.assertEqual(set(result), {"pypdf", "python-docx", "lxml", "typing_extensions"})
            for package, paths in result.items():
                with self.subTest(package=package):
                    self.assertTrue(paths)
                    for relative in paths:
                        file = output / relative
                        self.assertTrue(file.is_file())
                        self.assertGreater(file.stat().st_size, 80)
            self.assertTrue(any("LICENSES" in p.upper() for p in result["lxml"]))


if __name__ == "__main__":
    unittest.main()
