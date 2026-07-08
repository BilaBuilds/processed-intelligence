import json
import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = REPO_ROOT / "web"

LOCAL_PATH_MARKERS = [
    r"C:\\Users",
    r"C:\\Dev",
    r"/mnt/c",
    r"localhost",
    r"127\.0\.0\.1",
    r"\.env",
    r"\.sqlite",
    r"\.duckdb",
    r"warehouse",
]

SECRET_MARKERS = [
    r"AKIA[0-9A-Z]{16}",
    r"AIza[0-9A-Za-z_-]{20,}",
    r"gh[pousr]_[0-9A-Za-z_]+",
    r"sk-[A-Za-z0-9_-]{20,}",
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    r"api[_-]?key",
    r"client[_-]?secret",
    r"accountkey",
    r"sharedaccesssignature",
    r"authorization:\s*bearer",
    r"bearer\s+[A-Za-z0-9._-]{20,}",
    r"PORTAL_SESSION_TOKEN",
]


def public_files():
    return [
        path
        for path in WEB_ROOT.rglob("*")
        if path.is_file() and path.suffix.lower() in {".html", ".js", ".json", ".css"}
    ]


class StaticWebAppBundleTests(unittest.TestCase):
    def test_required_static_files_exist(self):
        self.assertTrue((WEB_ROOT / "index.html").is_file())
        self.assertTrue((WEB_ROOT / "dashboard.html").is_file())
        self.assertTrue((WEB_ROOT / "dashboard_data.js").is_file())

    def test_dashboard_references_data_file_relatively(self):
        dashboard = (WEB_ROOT / "dashboard.html").read_text(encoding="utf-8")

        self.assertIn('src="dashboard_data.js"', dashboard)
        self.assertNotIn('src="/dashboard_data.js"', dashboard)
        self.assertNotIn("http://", dashboard)
        self.assertNotIn("https://", dashboard.replace("https://fonts.googleapis.com", "").replace("https://fonts.gstatic.com", ""))

    def test_public_files_do_not_contain_local_paths(self):
        for path in public_files():
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(REPO_ROOT)):
                for marker in LOCAL_PATH_MARKERS:
                    self.assertNotRegex(text, marker)

    def test_public_files_do_not_contain_obvious_secret_markers(self):
        for path in public_files():
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(REPO_ROOT)):
                for marker in SECRET_MARKERS:
                    self.assertIsNone(re.search(marker, text, flags=re.IGNORECASE))

    def test_staticwebapp_config_is_valid_json_if_present(self):
        config = WEB_ROOT / "staticwebapp.config.json"
        if not config.exists():
            self.skipTest("staticwebapp.config.json not present")

        data = json.loads(config.read_text(encoding="utf-8"))
        self.assertIsInstance(data, dict)


if __name__ == "__main__":
    unittest.main()
