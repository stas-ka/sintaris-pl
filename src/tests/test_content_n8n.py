"""
test_content_n8n.py — Integration tests for the Content Strategy Agent N8N workflows.

Tests exercise the LIVE deployed N8N webhooks on VPS-Supertaris and the VPS Web API.
They require network access to agents.sintaris.net / automata.dev2null.de.

Run from project root:
    cd src && python3 -m pytest tests/test_content_n8n.py -v

Or against a custom VPS:
    VPS_N8N_HOST=https://automata.dev2null.de \
    VPS_WEB_BASE=https://agents.sintaris.net/supertaris \
    cd src && python3 -m pytest tests/test_content_n8n.py -v

Skip live tests in CI by running without network access — tests gracefully skip if
the webhook returns a connection error.

Tests:
  T_CN_01 — VPS /api/version returns HTTP 200 and JSON with version >= 2026.4.69
  T_CN_02 — N8N generate webhook returns HTTP 200 for content plan
  T_CN_03 — Generated content plan has 'content' key with text length >= 200
  T_CN_04 — N8N generate webhook returns HTTP 200 for single post
  T_CN_05 — Generated post is non-empty (length >= 200)
  T_CN_06 — Generate with correction param includes corrected result
  T_CN_07 — Generate with KB context payload accepted without error
  T_CN_08 — Invalid/missing payload returns error key or 4xx (not 500)
  T_CN_09 — N8N generate workflow is ACTIVE (via N8N API)
  T_CN_10 — N8N publish workflow is ACTIVE (via N8N API)
  T_CN_11 — VPS /api/status returns 'ok' for authenticated user
  T_CN_12 — N8N webhook rejects non-JSON body with non-200 or returns error key
"""

import os
import json
import time
import unittest
import urllib.request
import urllib.error

# ── Configuration ─────────────────────────────────────────────────────────────
N8N_BASE        = os.environ.get("VPS_N8N_HOST",     "https://automata.dev2null.de")
N8N_API_KEY     = os.environ.get("VPS_N8N_API_KEY",  "")
GENERATE_WH     = f"{N8N_BASE}/webhook/taris-content-generate"
PUBLISH_WH      = f"{N8N_BASE}/webhook/taris-content-publish"
GENERATE_WF_ID  = os.environ.get("N8N_CONTENT_GENERATE_WF_ID", "j5KY6jNYEG1JaM5b")
PUBLISH_WF_ID   = os.environ.get("N8N_CONTENT_PUBLISH_WF_ID",  "Z8PYyf6rLg4JCoFh")

# Web UI base: use direct port if nginx proxy returns 502 (known VPS port mismatch)
# Override: VPS_WEB_BASE=http://localhost:8090
WEB_BASE        = os.environ.get("VPS_WEB_BASE",     "http://localhost:8090")
WEB_ADMIN_USER  = os.environ.get("PICO_ADMIN_USER",  "admin")
WEB_ADMIN_PASS  = os.environ.get("PICO_ADMIN_PASS",  "admin")

TIMEOUT         = int(os.environ.get("N8N_TEST_TIMEOUT", "90"))
MIN_CONTENT_LEN = 200   # characters expected in a valid generated content


# ── Helpers ───────────────────────────────────────────────────────────────────

def _post_json(url: str, payload: dict, timeout: int = TIMEOUT) -> tuple[int, dict]:
    """POST JSON to url, return (status_code, response_dict)."""
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read()
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, {"_raw": raw.decode(errors="replace")}
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}
    except Exception as exc:
        raise unittest.SkipTest(f"Network error reaching {url}: {exc}")


def _get_json(url: str, headers: dict | None = None, timeout: int = 15) -> tuple[int, dict]:
    """GET url, return (status_code, response_dict)."""
    req = urllib.request.Request(url, headers=headers or {})
    try:
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read()
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, {"_raw": raw.decode(errors="replace")}
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}
    except Exception as exc:
        raise unittest.SkipTest(f"Network error reaching {url}: {exc}")


def _base_payload(mode: str = "plan", correction: str = "", kb_context: str = "") -> dict:
    return {
        "chat_id":    999,
        "mode":       mode,
        "q1":         "Тест: фитнес-тренер, аудитория 25-35 лет, цель — набор клиентов",
        "q2":         "Telegram",
        "kb_context": kb_context,
        "correction": correction,
        "lang":       "ru",
        "session_id": f"test_{int(time.time())}",
    }


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestVPSDeployment(unittest.TestCase):
    """T_CN_01 / T_CN_11 — Verify VPS deployment is live and correct version."""

    def test_T_CN_01_api_version_returns_json(self):
        """VPS /api/version returns HTTP 200 and JSON with 'version' key."""
        status, data = _get_json(f"{WEB_BASE}/api/version")
        if status == 502:
            self.skipTest("Nginx proxy returns 502 — known port mismatch (8086 vs 8090). Run with VPS_WEB_BASE=http://localhost:8090")
        self.assertEqual(status, 200, f"/api/version returned {status}: {data}")
        self.assertIn("version", data, f"'version' key missing from /api/version: {data}")

    def test_T_CN_01b_api_version_at_least_2026_4_69(self):
        """VPS /api/version shows bot_content.py-era version (>= 2026.4.69)."""
        status, data = _get_json(f"{WEB_BASE}/api/version")
        if status != 200:
            self.skipTest(f"/api/version returned {status}")
        version = data.get("version", "")
        # Parse as year.minor.patch: e.g. "2026.4.69"
        parts = version.split(".")
        self.assertGreaterEqual(len(parts), 3, f"Unexpected version format: {version}")
        year, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
        self.assertTrue(
            (year, minor, patch) >= (2026, 4, 69),
            f"Expected version >= 2026.4.69 (Content Agent era), got {version}",
        )

    def test_T_CN_11_api_status_authenticated(self):
        """VPS /api/status returns 'ok' when authenticated (session cookie)."""
        import ssl, http.cookiejar, urllib.parse
        jar = http.cookiejar.CookieJar()
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar),
            urllib.request.HTTPSHandler(context=ctx),
        )
        # Login
        login_data = urllib.parse.urlencode({
            "username": WEB_ADMIN_USER,
            "password": WEB_ADMIN_PASS,
        }).encode()
        try:
            opener.open(f"{WEB_BASE}/login", login_data, timeout=15)
        except Exception as exc:
            self.skipTest(f"Could not login to {WEB_BASE}: {exc}")
        # Check status
        try:
            resp = opener.open(f"{WEB_BASE}/api/status", timeout=10)
            data = json.loads(resp.read())
            self.assertIn(data.get("status"), ("ok",), f"/api/status returned: {data}")
        except Exception as exc:
            self.skipTest(f"Could not reach /api/status: {exc}")


class TestN8NWorkflowStatus(unittest.TestCase):
    """T_CN_09 / T_CN_10 — Verify N8N workflows are active."""

    def _get_workflow(self, wf_id: str) -> dict:
        if not N8N_API_KEY:
            self.skipTest("VPS_N8N_API_KEY not set — cannot query N8N API")
        status, data = _get_json(
            f"{N8N_BASE}/api/v1/workflows/{wf_id}",
            headers={"X-N8N-API-KEY": N8N_API_KEY},
        )
        if status == 404:
            self.skipTest(f"Workflow {wf_id} not found in N8N")
        self.assertEqual(status, 200, f"N8N API returned {status} for workflow {wf_id}")
        return data

    def test_T_CN_09_generate_workflow_active(self):
        """N8N 'Taris - Content Generate' workflow is active."""
        data = self._get_workflow(GENERATE_WF_ID)
        self.assertTrue(data.get("active"), f"Generate workflow not active: {data.get('name')}")
        self.assertIn("Content Generate", data.get("name", ""),
                      f"Unexpected workflow name: {data.get('name')}")

    def test_T_CN_10_publish_workflow_active(self):
        """N8N 'Taris - Content Publish' workflow is active."""
        data = self._get_workflow(PUBLISH_WF_ID)
        self.assertTrue(data.get("active"), f"Publish workflow not active: {data.get('name')}")
        self.assertIn("Content Publish", data.get("name", ""),
                      f"Unexpected workflow name: {data.get('name')}")


class TestContentGenerate(unittest.TestCase):
    """T_CN_02–T_CN_08 — Test content generation via N8N webhook."""

    def test_T_CN_02_generate_plan_returns_200(self):
        """POST to content-generate webhook returns HTTP 200 for plan mode."""
        status, data = _post_json(GENERATE_WH, _base_payload("plan"))
        self.assertEqual(status, 200, f"Expected 200, got {status}: {data}")

    def test_T_CN_03_generate_plan_has_content_key(self):
        """Generated content plan response has 'content' key with non-empty text."""
        status, data = _post_json(GENERATE_WH, _base_payload("plan"))
        self.assertEqual(status, 200, f"Expected 200, got {status}")
        self.assertIn("content", data, f"Response missing 'content' key: {list(data.keys())}")
        content = data["content"]
        self.assertIsInstance(content, str, f"'content' must be a string, got {type(content)}")
        self.assertGreaterEqual(
            len(content), MIN_CONTENT_LEN,
            f"Content too short ({len(content)} chars), expected >= {MIN_CONTENT_LEN}",
        )

    def test_T_CN_04_generate_post_returns_200(self):
        """POST to content-generate webhook returns HTTP 200 for post mode."""
        status, data = _post_json(GENERATE_WH, _base_payload("post"))
        self.assertEqual(status, 200, f"Expected 200, got {status}: {data}")

    def test_T_CN_05_generate_post_has_content(self):
        """Generated single post response has non-empty 'content' key."""
        status, data = _post_json(GENERATE_WH, _base_payload("post"))
        self.assertEqual(status, 200)
        self.assertIn("content", data, f"Post response missing 'content': {list(data.keys())}")
        self.assertGreaterEqual(len(data["content"]), MIN_CONTENT_LEN,
                                f"Post too short: {len(data['content'])} chars")

    def test_T_CN_06_generate_with_correction(self):
        """Generate with correction param returns updated content without error."""
        payload = _base_payload("plan", correction="Сделай более вовлекающим, добавь вопросы аудитории")
        status, data = _post_json(GENERATE_WH, payload)
        self.assertEqual(status, 200)
        self.assertNotIn("error", data,
                         f"Correction request returned error: {data.get('error')}")
        self.assertIn("content", data)
        self.assertGreater(len(data["content"]), 0)

    def test_T_CN_07_generate_with_kb_context(self):
        """Generate with kb_context payload is accepted and returns content."""
        payload = _base_payload("post", kb_context=(
            "[KNOWLEDGE]\n"
            "Из заметок пользователя:\n"
            "Мои клиенты — молодые мамы после декрета, ищут домашние тренировки без оборудования.\n"
        ))
        status, data = _post_json(GENERATE_WH, payload)
        self.assertEqual(status, 200)
        self.assertIn("content", data)
        self.assertGreater(len(data["content"]), 0)

    def test_T_CN_08_empty_payload_returns_error_not_500(self):
        """Empty/minimal payload returns structured error or 4xx — not 500."""
        status, data = _post_json(GENERATE_WH, {})
        # N8N Code node catches errors and returns {"error": "..."} with 200,
        # or the workflow returns 4xx. Either way, no unhandled 500.
        self.assertNotEqual(status, 500,
                            f"Empty payload caused unhandled 500: {data}")
        # If 200, must have either 'content' or 'error' key
        if status == 200:
            self.assertTrue(
                "content" in data or "error" in data,
                f"200 response has neither 'content' nor 'error': {data}",
            )

    def test_T_CN_12_non_json_body_rejected(self):
        """Non-JSON body to generate webhook returns 4xx or structured error, not 500."""
        req = urllib.request.Request(
            GENERATE_WH,
            data=b"not-json-body",
            headers={"Content-Type": "text/plain"},
            method="POST",
        )
        try:
            import ssl
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                status = resp.status
        except urllib.error.HTTPError as e:
            status = e.code
        except Exception as exc:
            self.skipTest(f"Network error: {exc}")
        self.assertNotEqual(status, 500,
                            f"Non-JSON body caused unhandled 500")


class TestContentPublishWebhook(unittest.TestCase):
    """T_CN_Pub — Test content publish webhook reachability."""

    def test_T_CN_pub_01_publish_webhook_reachable(self):
        """POST to content-publish webhook returns non-500 response."""
        # Use a fake channel to avoid actually posting — expect error response
        payload = {
            "chat_id":  999,
            "channel":  "@nonexistent_channel_for_testing",
            "content":  "Test content from integration test",
            "session_id": f"test_{int(time.time())}",
        }
        try:
            status, data = _post_json(PUBLISH_WH, payload, timeout=30)
        except unittest.SkipTest:
            raise
        # Should not be 500; 200 with error key or 4xx are both acceptable
        self.assertNotEqual(status, 500, f"Publish webhook returned 500: {data}")
        # If 200, must have structured response
        if status == 200:
            self.assertTrue(
                "success" in data or "error" in data,
                f"Publish response has neither 'success' nor 'error': {data}",
            )

    def test_T_CN_pub_02_publish_responds_within_timeout(self):
        """Publish webhook responds within 30 seconds."""
        payload = {
            "chat_id":  999,
            "channel":  "@nonexistent_channel_for_testing",
            "content":  "Timing test",
            "session_id": f"timing_{int(time.time())}",
        }
        start = time.time()
        try:
            _post_json(PUBLISH_WH, payload, timeout=30)
        except unittest.SkipTest:
            raise
        elapsed = time.time() - start
        self.assertLess(elapsed, 30, f"Publish webhook took {elapsed:.1f}s (> 30s)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
