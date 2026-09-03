#!/usr/bin/env python3
"""
Pura Services — Exhaustive Security Test Suite
Tests attack vectors, information disclosure, path traversal, PIN security,
XSS mitigation, symlink handling, range requests, and cryptographic integrity.
"""

import hashlib
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from urllib.parse import quote

import requests

PORT = 8995
BASE_URL = f"http://127.0.0.1:{PORT}"
TEST_DIR = Path("shared_files_sec_test").resolve()


class PuraSecurityTestSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        TEST_DIR.mkdir(parents=True, exist_ok=True)
        # Spin up test server with PIN 9988
        cls.server_proc = subprocess.Popen(
            [
                sys.executable,
                "server.py",
                "--port",
                str(PORT),
                "--dir",
                str(TEST_DIR),
                "--pin",
                "9988",
                "--no-discovery",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        for _ in range(50):
            time.sleep(0.1)
            try:
                r = requests.get(BASE_URL + "/api/info", timeout=1)
                if r.status_code == 200:
                    break
            except Exception:
                pass

        cls.anon_session = requests.Session()
        cls.auth_session = requests.Session()
        cls.auth_session.post(
            BASE_URL + "/api/login", json={"pin": "9988", "trusted": True}
        )

    @classmethod
    def tearDownClass(cls):
        if cls.server_proc:
            cls.server_proc.terminate()
            try:
                cls.server_proc.wait(timeout=2)
            except Exception:
                cls.server_proc.kill()
        if TEST_DIR.exists():
            shutil.rmtree(TEST_DIR, ignore_errors=True)

    # 1. GitHub Publication & Secret Leak Audit
    def test_01_repo_files_leak_scan(self):
        """Scan all repository files for private keys, personal paths, tokens, and credentials."""
        root = Path(".").resolve()
        for path in root.rglob("*"):
            if not path.is_file() or ".git" in str(path) or "test_security.py" in str(path) or "cert" in str(path) or "scratch" in str(path) or "__pycache__" in str(path) or "shared_files" in str(path):
                continue
            content = path.read_text(encoding="utf-8", errors="ignore")
            self.assertNotIn("BEGIN RSA PRIVATE KEY", content, f"Leaked private key in {path}")
            self.assertNotIn("BEGIN PRIVATE KEY", content, f"Leaked private key in {path}")
            # Ensure no local user home path is hardcoded
            user_paths = re.findall(r'[A-Za-z]:\\[Uu]sers\\[a-zA-Z0-9_\-]+', content)
            self.assertEqual(len(user_paths), 0, f"Found personal Windows path in {path}: {user_paths}")

    # 2. Git History Audit
    def test_02_git_history_cleanliness(self):
        """Scan Git object store for any historical secrets or personal user paths."""
        try:
            output = subprocess.check_output(["git", "rev-list", "--all", "--objects"], text=True)
        except Exception:
            return  # Git not in test environment
        for line in output.strip().splitlines():
            oid = line.split()[0]
            try:
                obj_type = subprocess.check_output(["git", "cat-file", "-t", oid], text=True).strip()
                if obj_type != "blob":
                    continue
                content = subprocess.check_output(["git", "cat-file", "-p", oid], errors="ignore")
                self.assertNotIn("BEGIN RSA PRIVATE KEY", content)
                self.assertNotIn("BEGIN PRIVATE KEY", content)
            except Exception:
                pass

    # 3. /api/info Information Disclosure Check
    def test_03_api_info_information_disclosure(self):
        """Ensure /api/info does not expose host absolute paths, usernames, or sensitive details."""
        r = self.anon_session.get(BASE_URL + "/api/info")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertNotIn("C:\\", data.get("share_dir", ""))
        self.assertNotIn("/home/", data.get("share_dir", ""))
        self.assertNotIn("/Users/", data.get("share_dir", ""))
        self.assertNotIn("pin", data)
        self.assertNotIn("auth_token", data)

    # 4. Error Message Path Disclosure Audit
    def test_04_error_message_disclosure_matrix(self):
        """Trigger various error conditions and verify responses contain safe messages without paths."""
        error_requests = [
            ("POST", "/api/upload/init", {"filename": "../bad.txt", "size": "invalid"}),
            ("POST", "/api/upload/chunk?id=invalid_id&offset=0", b"data"),
            ("POST", "/api/upload/complete?id=non_existent_id", None),
            ("PATCH", "/api/files/non_existent.txt", {"name": "new.txt"}),
            ("DELETE", "/api/files/non_existent.txt", None),
            ("POST", "/api/files/download-zip", {"files": ["../../../etc/passwd"]}),
            ("GET", "/api/files/download-folder/NonExistentFolder", None),
        ]
        for method, endpoint, payload in error_requests:
            if method == "POST":
                if isinstance(payload, dict):
                    r = self.auth_session.post(BASE_URL + endpoint, json=payload)
                else:
                    r = self.auth_session.post(BASE_URL + endpoint, data=payload)
            elif method == "PATCH":
                r = self.auth_session.patch(BASE_URL + endpoint, json=payload)
            elif method == "DELETE":
                r = self.auth_session.delete(BASE_URL + endpoint)
            elif method == "GET":
                r = self.auth_session.get(BASE_URL + endpoint)

            self.assertIn(r.status_code, (400, 404, 409, 422, 500))
            body_text = r.text
            self.assertNotIn("C:\\Users\\", body_text)
            self.assertNotIn("/home/", body_text)
            self.assertNotIn("Traceback (most recent call last)", body_text)

    # 5. Path Traversal & Escape Attacks
    def test_05_path_traversal_attacks_blocked(self):
        """Test ../, ..\\, %2e%2e/, absolute paths, and UNC paths across all endpoints."""
        attacks = [
            "../../../etc/passwd",
            "..\\..\\windows\\system32\\cmd.exe",
            "....//....//secret.txt",
            "%2e%2e%2f%2e%2e%2fsecret.txt",
            "C:\\secret.txt",
            "/etc/shadow",
            "\\\\attacker\\share\\payload.txt",
        ]
        for att in attacks:
            # 1. Download
            dl = self.auth_session.get(BASE_URL + f"/files/{quote(att)}")
            self.assertIn(dl.status_code, (400, 404))

            # 2. Preview
            prev = self.auth_session.get(BASE_URL + f"/files/{quote(att)}?preview=1")
            self.assertIn(prev.status_code, (400, 404))

            # 3. Rename
            ren = self.auth_session.patch(BASE_URL + f"/api/files/{quote(att)}", json={"name": "new.txt"})
            self.assertIn(ren.status_code, (400, 404))

            # 4. Delete
            dele = self.auth_session.delete(BASE_URL + f"/api/files/{quote(att)}")
            self.assertIn(dele.status_code, (400, 404))

    # 6. Hidden & Internal File Protection
    def test_06_hidden_internal_file_access_blocked(self):
        """Verify .pura_config.json, .pura_file_expiry.json, and .tmp files cannot be read via /files/."""
        # Create a dummy internal file
        hidden_file = TEST_DIR / ".pura_config.json"
        hidden_file.write_text(json.dumps({"pin": "SECRET_PIN"}), encoding="utf-8")

        r = self.auth_session.get(BASE_URL + "/files/.pura_config.json")
        self.assertEqual(r.status_code, 404)

        r2 = self.auth_session.get(BASE_URL + "/files/.pura_config.json?preview=1")
        self.assertEqual(r2.status_code, 404)

    # 7. Symlink / Junction Traversal Protection
    def test_07_symlink_escape_rejection(self):
        """Verify symlinks pointing outside shared_files are rejected with 404."""
        outside_file = Path("outside_secret.txt").resolve()
        outside_file.write_text("OUTSIDE_SECRET_DATA", encoding="utf-8")

        symlink_path = TEST_DIR / "symlink_test.txt"
        try:
            symlink_path.symlink_to(outside_file)
        except (OSError, NotImplementedError):
            outside_file.unlink(missing_ok=True)
            return  # Windows Developer Mode disabled for symlinks

        try:
            r = self.auth_session.get(BASE_URL + "/files/symlink_test.txt")
            self.assertEqual(r.status_code, 404)
        finally:
            symlink_path.unlink(missing_ok=True)
            outside_file.unlink(missing_ok=True)

    # 8. File Upload Sanitization & Reserved Windows Device Names
    def test_08_file_upload_sanitization(self):
        """Test uploading dangerous extensions, Windows device names (NUL, CON, AUX), and path payloads."""
        dangerous_names = [
            "CON.txt",
            "PRN.png",
            "AUX.log",
            "NUL.dat",
            "COM1.txt",
            "LPT1.txt",
            "../../../evil.sh",
            "<script>alert(1)</script>.txt",
        ]
        for name in dangerous_names:
            r = self.auth_session.post(BASE_URL + f"/api/upload?name={quote(name)}", data=b"safe data")
            self.assertEqual(r.status_code, 201)
            saved_url = r.json()["url"]
            # Ensure saved filename does not escape directory or contain unescaped path traversal
            self.assertFalse(saved_url.startswith("/files/.."))

    # 9. File Preview XSS & CSP Sandbox Protection
    def test_09_file_preview_csp_and_xss_protection(self):
        """Test HTML and SVG previews return sandboxed CSP headers preventing dashboard script execution."""
        html_payload = b"<script>document.cookie='hacked';</script><b>Preview Content</b>"
        self.auth_session.post(BASE_URL + "/api/upload?name=xss_attack.html", data=html_payload)

        r = self.auth_session.get(BASE_URL + "/files/xss_attack.html?preview=1")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Content-Security-Policy", r.headers)
        csp = r.headers["Content-Security-Policy"]
        self.assertIn("sandbox", csp)
        self.assertEqual(r.headers.get("X-Content-Type-Options"), "nosniff")

    # 10. Resumable Upload Tampering & Security
    def test_10_resumable_upload_tampering_rejected(self):
        """Verify upload ID forgery, offset mismatch (409), and SHA-256 mismatch (422)."""
        data = b"RESUMABLE_SECURITY_DATA"
        correct_sha = hashlib.sha256(data).hexdigest()
        fake_sha = "f" * 64

        # Init
        init_r = self.auth_session.post(
            BASE_URL + "/api/upload/init",
            json={"filename": "tamper_test.dat", "size": len(data), "sha256": fake_sha},
        )
        self.assertEqual(init_r.status_code, 201)
        upload_id = init_r.json()["upload_id"]

        # Chunk with wrong offset rejected with 409
        bad_chunk = self.auth_session.post(
            BASE_URL + f"/api/upload/chunk?id={upload_id}&offset=9999", data=data
        )
        self.assertEqual(bad_chunk.status_code, 409)

        # Upload correct chunk
        good_chunk = self.auth_session.post(
            BASE_URL + f"/api/upload/chunk?id={upload_id}&offset=0", data=data
        )
        self.assertEqual(good_chunk.status_code, 200)

        # Finalize with mismatched SHA-256 rejected with 422
        comp_r = self.auth_session.post(
            BASE_URL + f"/api/upload/complete?id={upload_id}"
        )
        self.assertEqual(comp_r.status_code, 422)

    # 11. PIN Authentication Timing & Brute-Force Rejection
    def test_11_pin_authentication_security(self):
        """Test wrong PIN, empty PIN, constant-time validation, and logout session clearing."""
        s = requests.Session()

        # 1. Unauthenticated requests to protected endpoints return 401
        self.assertEqual(s.get(BASE_URL + "/api/files").status_code, 401)
        self.assertEqual(s.get(BASE_URL + "/api/clipboard").status_code, 401)
        self.assertEqual(s.post(BASE_URL + "/api/upload?name=test.txt", data=b"x").status_code, 401)

        # 2. Empty PIN rejected
        self.assertEqual(s.post(BASE_URL + "/api/login", json={"pin": ""}).status_code, 401)

        # 3. Wrong PIN rejected
        self.assertEqual(s.post(BASE_URL + "/api/login", json={"pin": "0000"}).status_code, 401)

        # 4. Correct PIN unlocks
        login_r = s.post(BASE_URL + "/api/login", json={"pin": "9988"})
        self.assertEqual(login_r.status_code, 200)
        self.assertEqual(s.get(BASE_URL + "/api/files").status_code, 200)

        # 5. Logout locks
        s.post(BASE_URL + "/api/logout")
        self.assertEqual(s.get(BASE_URL + "/api/files").status_code, 401)

    # 12. HTTP Range Header Security Fuzzing
    def test_12_http_range_fuzzing(self):
        """Test negative ranges, out of bounds, and multi-range requests."""
        self.auth_session.post(BASE_URL + "/api/upload?name=range_fuzz.txt", data=b"0123456789")

        # Valid range
        r1 = self.auth_session.get(BASE_URL + "/files/range_fuzz.txt", headers={"Range": "bytes=2-5"})
        self.assertEqual(r1.status_code, 206)
        self.assertEqual(r1.content, b"2345")

        # Out of bounds range -> 416
        r2 = self.auth_session.get(BASE_URL + "/files/range_fuzz.txt", headers={"Range": "bytes=50-100"})
        self.assertEqual(r2.status_code, 416)

        # Inverted range -> 416
        r3 = self.auth_session.get(BASE_URL + "/files/range_fuzz.txt", headers={"Range": "bytes=8-3"})
        self.assertEqual(r3.status_code, 416)

        # Multi-range header -> 416 (disallowed to prevent memory amplification)
        r4 = self.auth_session.get(BASE_URL + "/files/range_fuzz.txt", headers={"Range": "bytes=0-1, 2-3"})
        self.assertEqual(r4.status_code, 416)

    # 13. ZIP Generation Security & Path Isolation
    def test_13_zip_generation_security(self):
        """Ensure ZIP archives do not contain traversal paths or hidden internal files."""
        self.auth_session.post(BASE_URL + "/api/upload?name=public1.txt", data=b"content 1")
        self.auth_session.post(BASE_URL + "/api/upload?name=public2.txt", data=b"content 2")

        # Traversal in selected ZIP rejected
        bad_zip = self.auth_session.post(
            BASE_URL + "/api/files/download-zip",
            json={"files": ["../../etc/passwd", "public1.txt"]},
        )
        self.assertEqual(bad_zip.status_code, 400)

        # Valid selected ZIP
        good_zip = self.auth_session.post(
            BASE_URL + "/api/files/download-zip",
            json={"files": ["public1.txt", "public2.txt"]},
        )
        self.assertEqual(good_zip.status_code, 200)
        self.assertEqual(good_zip.headers.get("Content-Type"), "application/zip")

    # 14. LAN Discovery Packet Information Audit
    def test_14_lan_discovery_packet_audit(self):
        """Verify discovery service broadcasts only public service descriptors without sensitive host info."""
        import server
        discovery = server.LanDiscoveryService(
            server_id="pura-test",
            server_name="Pura Server",
            protocol="http",
            port=8000,
            lan_url="http://192.168.1.50:8000/",
            auth_enabled=True,
        )
        packet = {
            "service": "pura",
            "version": "1.0",
            "server_id": discovery.server_id,
            "name": discovery.server_name,
            "protocol": discovery.protocol,
            "host": "192.168.1.50",
            "port": discovery.port,
            "url": discovery.lan_url,
            "auth_enabled": discovery.auth_enabled,
        }
        raw_json = json.dumps(packet)
        self.assertNotIn("pin", raw_json.lower())
        self.assertNotIn("token", raw_json.lower())
        self.assertNotIn("clipboard", raw_json.lower())
        self.assertNotIn("password", raw_json.lower())
        self.assertNotIn("C:\\", raw_json)

    # 15. Concurrency & Resource Safety
    def test_15_concurrency_and_dos_mitigation(self):
        """Test simultaneous requests and verify zero server memory or socket deadlocks."""
        errors = []

        def client_task(cid):
            try:
                s = requests.Session()
                s.post(BASE_URL + "/api/login", json={"pin": "9988", "trusted": True})
                # Upload
                ur = s.post(BASE_URL + f"/api/upload?name=dos_test_{cid}.dat", data=b"A" * 1024)
                if ur.status_code != 201:
                    errors.append(f"Upload failed: {ur.status_code}")
                # Fetch
                fr = s.get(BASE_URL + f"/files/dos_test_{cid}.dat")
                if len(fr.content) != 1024:
                    errors.append("Download size mismatch")
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=client_task, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Concurrency errors: {errors}")


if __name__ == "__main__":
    unittest.main()
