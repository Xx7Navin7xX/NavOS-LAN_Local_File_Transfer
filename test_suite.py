"""
Pura Services - Comprehensive Functional & Integration Test Suite
Verifies all core capabilities, endpoints, security, protocols, and TLS.
"""

import hashlib
import io
import json
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.parse
from pathlib import Path

import requests

PORT = 8998
BASE_URL = f"http://127.0.0.1:{PORT}"
PIN = "4321"
TEST_DIR = Path("shared_files_test").resolve()


class PuraFunctionalTestSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        TEST_DIR.mkdir(parents=True, exist_ok=True)
        cls.server_proc = subprocess.Popen(
            [
                sys.executable,
                "server.py",
                "--port",
                str(PORT),
                "--dir",
                str(TEST_DIR),
                "--pin",
                PIN,
                "--no-discovery",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        server_ready = False
        for _ in range(50):
            time.sleep(0.1)
            try:
                r = requests.get(BASE_URL + "/api/info", timeout=1)
                if r.status_code == 200:
                    server_ready = True
                    break
            except Exception:
                pass

        if not server_ready:
            cls.tearDownClass()
            raise RuntimeError(f"Test server failed to start on port {PORT}")

        cls.anon_session = requests.Session()
        cls.auth_session = requests.Session()
        login_res = cls.auth_session.post(
            BASE_URL + "/api/login", json={"pin": PIN, "trusted": True}
        )
        if login_res.status_code != 200:
            cls.tearDownClass()
            raise RuntimeError("Failed to authenticate session with server")

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "server_proc") and cls.server_proc:
            cls.server_proc.terminate()
            try:
                cls.server_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                cls.server_proc.kill()
        if TEST_DIR.exists():
            shutil.rmtree(TEST_DIR, ignore_errors=True)

    def setUp(self):
        for item in TEST_DIR.iterdir():
            if item.name.startswith(".pura") or item.name == "clipboard_texts":
                continue
            try:
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
            except OSError:
                pass

    # 1. Server Startup and Health
    def test_01_startup_and_info(self):
        r = self.anon_session.get(BASE_URL + "/api/info")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data.get("share_dir"), TEST_DIR.name)
        self.assertTrue(data.get("auth_enabled"))
        self.assertTrue(data.get("has_pin"))
        self.assertFalse(data.get("is_authenticated"))

        r_auth = self.auth_session.get(BASE_URL + "/api/info")
        self.assertEqual(r_auth.status_code, 200)
        self.assertTrue(r_auth.json().get("is_authenticated"))

    # 2. Static Asset Serving
    def test_02_static_assets_serving(self):
        # Index HTML
        r = self.anon_session.get(BASE_URL + "/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/html", r.headers.get("Content-Type", ""))
        self.assertIn("Pura", r.text)

        # Asset serving (e.g. GooglePay_QR.png if present in assets)
        r_asset = self.anon_session.get(BASE_URL + "/assets/GooglePay_QR.png")
        if (Path("assets") / "GooglePay_QR.png").exists():
            self.assertEqual(r_asset.status_code, 200)
            self.assertIn("image/png", r_asset.headers.get("Content-Type", ""))

        # Android / touch scroll chaining support
        self.assertIn("overscroll-behavior: auto", r.text)
        self.assertIn("initAndroidScrollChaining", r.text)

    # 3. Direct File Upload and Listing
    def test_03_file_upload_and_listing(self):
        content = b"Hello, Pura Services!"
        filename = "hello_world.txt"

        r = self.auth_session.post(
            BASE_URL + f"/api/upload?name={filename}", data=content
        )
        self.assertIn(r.status_code, (200, 201))

        r_list = self.auth_session.get(BASE_URL + "/api/files")
        self.assertEqual(r_list.status_code, 200)
        files = r_list.json()["files"]
        match = next((f for f in files if f["name"] == filename), None)
        self.assertIsNotNone(match)
        self.assertEqual(match["size"], len(content))

    # 4. File Download and Range Requests
    def test_04_file_download_and_range(self):
        data = b"0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        filename = "alphabet.dat"
        self.auth_session.post(BASE_URL + f"/api/upload?name={filename}", data=data)

        # Full download
        r_full = self.auth_session.get(BASE_URL + f"/files/{filename}")
        self.assertEqual(r_full.status_code, 200)
        self.assertEqual(r_full.content, data)

        # Partial range request (bytes 0-9)
        r_range = self.auth_session.get(
            BASE_URL + f"/files/{filename}", headers={"Range": "bytes=0-9"}
        )
        self.assertEqual(r_range.status_code, 206)
        self.assertEqual(r_range.content, b"0123456789")
        self.assertEqual(
            r_range.headers.get("Content-Range"), f"bytes 0-9/{len(data)}"
        )

        # Suffix range request (last 5 bytes)
        r_suffix = self.auth_session.get(
            BASE_URL + f"/files/{filename}", headers={"Range": "bytes=31-35"}
        )
        self.assertEqual(r_suffix.status_code, 206)
        self.assertEqual(r_suffix.content, b"VWXYZ")

    # 5. File Deletion
    def test_05_file_deletion(self):
        filename = "to_delete.txt"
        self.auth_session.post(
            BASE_URL + f"/api/upload?name={filename}", data=b"delete me"
        )
        self.assertTrue((TEST_DIR / filename).exists())

        r_del = self.auth_session.delete(BASE_URL + f"/api/files/{filename}")
        self.assertEqual(r_del.status_code, 200)
        self.assertFalse((TEST_DIR / filename).exists())

    # 6. Resumable Chunked Upload
    def test_06_resumable_upload_lifecycle(self):
        chunk1 = b"Part 1 - 1234567890\n"
        chunk2 = b"Part 2 - ABCDEFGHIJ\n"
        total_data = chunk1 + chunk2
        total_sha = hashlib.sha256(total_data).hexdigest()
        filename = "resumable_doc.txt"

        # 1. Init
        r_init = self.auth_session.post(
            BASE_URL + "/api/upload/init",
            json={"filename": filename, "size": len(total_data), "sha256": total_sha},
        )
        self.assertEqual(r_init.status_code, 201)
        upload_id = r_init.json()["upload_id"]

        # 2. Chunk 1
        r_c1 = self.auth_session.post(
            BASE_URL + f"/api/upload/chunk?id={upload_id}&offset=0", data=chunk1
        )
        self.assertEqual(r_c1.status_code, 200)

        # 3. Check status
        r_stat = self.auth_session.get(BASE_URL + f"/api/upload/status?id={upload_id}")
        self.assertEqual(r_stat.status_code, 200)
        self.assertEqual(r_stat.json()["received"], len(chunk1))

        # 4. Chunk 2
        r_c2 = self.auth_session.post(
            BASE_URL + f"/api/upload/chunk?id={upload_id}&offset={len(chunk1)}",
            data=chunk2,
        )
        self.assertEqual(r_c2.status_code, 200)

        # 5. Complete
        r_comp = self.auth_session.post(
            BASE_URL + f"/api/upload/complete?id={upload_id}"
        )
        self.assertIn(r_comp.status_code, (200, 201))

        final_file = TEST_DIR / filename
        self.assertTrue(final_file.exists())
        self.assertEqual(final_file.read_bytes(), total_data)

    # 7. Resumable Upload Integrity Rejection (422)
    def test_07_resumable_upload_sha256_verification(self):
        data = b"Genuine data content"
        mismatched_sha = "0" * 64
        filename = "checksum_fail.txt"

        r_init = self.auth_session.post(
            BASE_URL + "/api/upload/init",
            json={"filename": filename, "size": len(data), "sha256": mismatched_sha},
        )
        self.assertEqual(r_init.status_code, 201)
        upload_id = r_init.json()["upload_id"]

        self.auth_session.post(
            BASE_URL + f"/api/upload/chunk?id={upload_id}&offset=0", data=data
        )

        r_comp = self.auth_session.post(
            BASE_URL + f"/api/upload/complete?id={upload_id}"
        )
        self.assertEqual(r_comp.status_code, 422)
        self.assertFalse((TEST_DIR / filename).exists())

    # 8. Folder Upload with Directory Preservation
    def test_08_folder_upload(self):
        nested_rel = "my_project/src/main.py"
        code = b"print('nested file')"

        r = self.auth_session.post(
            BASE_URL + f"/api/upload?name={nested_rel}&folder=1", data=code
        )
        self.assertIn(r.status_code, (200, 201))

        target_path = TEST_DIR / "my_project" / "src" / "main.py"
        self.assertTrue(target_path.exists())
        self.assertEqual(target_path.read_bytes(), code)

    # 9. ZIP Download of Selected Files & Folders
    def test_09_download_selected_zip(self):
        (TEST_DIR / "file1.txt").write_text("content 1", encoding="utf-8")
        (TEST_DIR / "folderA").mkdir(parents=True, exist_ok=True)
        (TEST_DIR / "folderA" / "subfile.txt").write_text(
            "sub content", encoding="utf-8"
        )

        r = self.auth_session.post(
            BASE_URL + "/api/files/download-zip",
            json={"files": ["file1.txt", "folderA"]},
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("application/zip", r.headers.get("Content-Type", ""))

        import zipfile

        zip_buf = io.BytesIO(r.content)
        with zipfile.ZipFile(zip_buf, "r") as zf:
            namelist = zf.namelist()
            self.assertIn("file1.txt", namelist)
            self.assertTrue(any("subfile.txt" in n for n in namelist))

    # 10. Folder Download as ZIP
    def test_10_download_folder_zip(self):
        folder = TEST_DIR / "my_docs"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "doc.txt").write_text("document text", encoding="utf-8")

        r = self.auth_session.get(BASE_URL + "/api/files/download-folder/my_docs")
        self.assertEqual(r.status_code, 200)
        self.assertIn("application/zip", r.headers.get("Content-Type", ""))

    # 11. Clipboard Functionality
    def test_11_clipboard_crud(self):
        test_text = "Important secret token: 994411"

        # Create
        r_add = self.auth_session.post(
            BASE_URL + "/api/clipboard", json={"text": test_text}
        )
        self.assertIn(r_add.status_code, (200, 201))
        res_data = r_add.json()
        item = res_data.get("item", res_data)
        item_id = item["id"]

        # Read
        r_get = self.auth_session.get(BASE_URL + "/api/clipboard")
        self.assertEqual(r_get.status_code, 200)
        items = r_get.json().get("items", [])
        match = next((i for i in items if str(i["id"]) == str(item_id)), None)
        self.assertIsNotNone(match)
        self.assertEqual(match["text"], test_text)

        # Delete
        r_del = self.auth_session.delete(BASE_URL + f"/api/clipboard/{item_id}")
        self.assertEqual(r_del.status_code, 200)

        # Verify deletion
        r_get_after = self.auth_session.get(BASE_URL + "/api/clipboard")
        items_after = r_get_after.json().get("items", [])
        self.assertFalse(any(str(i["id"]) == str(item_id) for i in items_after))

    # 12. File Search & Filtering
    def test_12_files_and_clipboard_search_data(self):
        (TEST_DIR / "quantum_algorithm.py").write_text(
            "# quantum simulation", encoding="utf-8"
        )
        self.auth_session.post(
            BASE_URL + "/api/clipboard", json={"text": "quantum computing notes"}
        )

        files = self.auth_session.get(BASE_URL + "/api/files").json().get("files", [])
        clips = self.auth_session.get(BASE_URL + "/api/clipboard").json().get("items", [])

        query = "quantum"
        matching_files = [f for f in files if query in f["name"].lower()]
        matching_clips = [c for c in clips if query in c["text"].lower()]

        self.assertTrue(len(matching_files) >= 1)
        self.assertTrue(len(matching_clips) >= 1)

    # 13. File Preview Header Controls
    def test_13_file_preview_safety(self):
        (TEST_DIR / "preview.txt").write_text("Hello preview", encoding="utf-8")
        r_txt = self.auth_session.get(BASE_URL + "/files/preview.txt?preview=1")
        self.assertEqual(r_txt.status_code, 200)
        self.assertIn("inline", r_txt.headers.get("Content-Disposition", ""))

        (TEST_DIR / "xss_attempt.html").write_text(
            "<script>alert(1)</script>", encoding="utf-8"
        )
        r_html = self.auth_session.get(BASE_URL + "/files/xss_attempt.html?preview=1")
        self.assertEqual(r_html.status_code, 200)
        content_type = r_html.headers.get("Content-Type", "").lower()
        self.assertNotIn("text/html", content_type)

    # 14. Real-time Events (SSE) Header & Format
    def test_14_sse_endpoint_headers(self):
        r = self.auth_session.get(
            BASE_URL + "/api/events", stream=True, timeout=3
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/event-stream", r.headers.get("Content-Type", ""))
        self.assertIn("no-cache", r.headers.get("Cache-Control", ""))

    # 15. Path Traversal & Security Constraints
    def test_15_path_traversal_prevention(self):
        # Folder upload with directory traversal is rejected with 400
        r_up = self.auth_session.post(
            BASE_URL + "/api/upload?name=../../escaped.txt&folder=1", data=b"hacked"
        )
        self.assertEqual(r_up.status_code, 400)
        self.assertFalse((TEST_DIR.parent / "escaped.txt").exists())

        # Direct file download attempting to escape share dir is blocked
        r_down = self.auth_session.get(BASE_URL + "/files/../../server.py")
        self.assertIn(r_down.status_code, (400, 403, 404))

    # 16. PIN Protection & Authentication Lifecycle
    def test_16_pin_auth_lifecycle(self):
        test_client = requests.Session()

        self.assertEqual(
            test_client.get(BASE_URL + "/api/files").status_code, 401
        )

        r_wrong = test_client.post(
            BASE_URL + "/api/login", json={"pin": "0000"}
        )
        self.assertEqual(r_wrong.status_code, 401)

        r_ok = test_client.post(BASE_URL + "/api/login", json={"pin": PIN})
        self.assertEqual(r_ok.status_code, 200)

        self.assertEqual(test_client.get(BASE_URL + "/api/files").status_code, 200)

        r_logout = test_client.post(BASE_URL + "/api/logout")
        self.assertEqual(r_logout.status_code, 200)
        self.assertEqual(
            test_client.get(BASE_URL + "/api/files").status_code, 401
        )

    # 17. Self-Signed Certificate Generation with Subject Alternative Names (SAN)
    def test_17_certificate_generation_san(self):
        from server import generate_self_signed_cert, cert_matches_lan_ips, get_all_lan_ips
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            cert_file = temp_path / "test_server.crt"
            key_file = temp_path / "test_server.key"

            generated = generate_self_signed_cert(cert_file, key_file)
            self.assertTrue(generated)
            self.assertTrue(cert_file.exists())
            self.assertTrue(key_file.exists())

            lan_ips = get_all_lan_ips()
            matches = cert_matches_lan_ips(cert_file, expected_ips=lan_ips, expected_dns=["localhost"])
            self.assertTrue(matches)

    # 18. Windows Reserved Filename Protection
    def test_18_windows_reserved_names(self):
        from server import sanitize_filename
        self.assertTrue(sanitize_filename("CON.txt").startswith("_"))
        self.assertTrue(sanitize_filename("NUL.dat").startswith("_"))
        self.assertTrue(sanitize_filename("PRN").startswith("_"))
        self.assertTrue(sanitize_filename("COM1.log").startswith("_"))

    # 19. LAN Discovery Service & Peer Tracking
    def test_19_lan_discovery_service(self):
        from server import LanDiscoveryService
        service = LanDiscoveryService(
            server_id="test-srv-123",
            server_name="TestMachine",
            protocol="http",
            port=8000,
            lan_url="http://192.168.1.50:8000/",
            auth_enabled=False,
        )
        self.assertEqual(service.server_id, "test-srv-123")
        self.assertEqual(service.server_name, "TestMachine")
        self.assertEqual(service.port, 8000)
        self.assertEqual(service.get_peers(), [])


if __name__ == "__main__":
    unittest.main()
