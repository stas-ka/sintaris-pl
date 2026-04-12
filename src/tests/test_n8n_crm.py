"""
test_n8n_crm.py — Unit tests for N8N adapter and CRM module.

Run (on target with bot.env):
  PYTHONPATH=~/.taris python -m pytest tests/test_n8n_crm.py -v

Run (offline, source inspection only):
  python src/tests/test_n8n_crm.py

Tests verify:
  - N8N adapter: config detection, URL building, webhook routing
  - CRM module: availability check, intent classification, contact operations
  - CRM store: schema expectations, function signatures
  - Bot_config: N8N/CRM constants present
  - i18n: all keys present in all 3 languages
"""

import json
import os
import sys
from pathlib import Path

_src = Path(__file__).parent.parent
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))


def _can_import_bot_config() -> bool:
    """Check if we can import bot_config (requires BOT_TOKEN)."""
    try:
        import core.bot_config
        return True
    except (SystemExit, RuntimeError, Exception):
        return False


_HAS_BOT_CONFIG = _can_import_bot_config()


# ─────────────────────────────────────────────────────────────────────────────
# T40: N8N config constants (source inspection — works offline)
# ─────────────────────────────────────────────────────────────────────────────

def test_n8n_config_constants_source():
    """T40: N8N config constants exist in bot_config.py source."""
    cfg_src = (_src / "core" / "bot_config.py").read_text(encoding="utf-8")
    for const in ("N8N_URL", "N8N_API_KEY", "N8N_WEBHOOK_SECRET", "N8N_TIMEOUT",
                   "CRM_ENABLED", "CRM_PG_DSN"):
        assert const in cfg_src, f"Missing constant: {const}"


# ─────────────────────────────────────────────────────────────────────────────
# T41: CRM config constants
# ─────────────────────────────────────────────────────────────────────────────

def test_crm_config_constants_source():
    """T41: CRM_ENABLED is bool, CRM_PG_DSN is str in source."""
    cfg_src = (_src / "core" / "bot_config.py").read_text(encoding="utf-8")
    assert 'CRM_ENABLED' in cfg_src
    assert 'os.environ.get("CRM_ENABLED"' in cfg_src
    assert 'CRM_PG_DSN' in cfg_src


# ─────────────────────────────────────────────────────────────────────────────
# T42: N8N adapter module structure (source inspection)
# ─────────────────────────────────────────────────────────────────────────────

def test_n8n_adapter_functions_source():
    """T42: bot_n8n.py defines required public functions (webhook-first design)."""
    src = (_src / "features" / "bot_n8n.py").read_text(encoding="utf-8")
    required = [
        # Webhook-first interface (technology-agnostic)
        "def call_webhook", "def trigger_workflow", "def is_configured",
        "def _build_auth_headers", "def verify_incoming_signature",
        # N8N admin API (optional, introspection only)
        "def list_workflows", "def get_execution", "def list_executions",
        "def test_connection", "def is_admin_api_configured",
        # Callback dispatch
        "def register_callback", "def process_callback",
    ]
    for fn in required:
        assert fn in src, f"bot_n8n.py missing: {fn}"

    # Auth types must all be handled
    for auth_type in ("bearer", "apikey", "hmac", "basic", "none"):
        assert auth_type in src, f"bot_n8n.py missing auth_type handling: {auth_type}"

    # No N8N-specific SDK imports
    assert "import n8n" not in src, "bot_n8n.py must not import n8n SDK"
    assert "from n8n" not in src, "bot_n8n.py must not import from n8n SDK"


# ─────────────────────────────────────────────────────────────────────────────
# T43: CRM module structure (source inspection)
# ─────────────────────────────────────────────────────────────────────────────

def test_crm_module_functions_source():
    """T43: bot_crm.py defines required public functions."""
    src = (_src / "features" / "bot_crm.py").read_text(encoding="utf-8")
    required = [
        "def is_available", "def add_contact", "def get_contact", "def search",
        "def list_contacts", "def delete_contact", "def update_contact",
        "def ai_tag_contact", "def ai_match_contacts",
        "def add_task", "def list_tasks", "def complete_task",
        "def create_campaign", "def match_campaign_contacts",
        "def get_campaign_contacts", "def approve_campaign",
        "def get_stats", "def classify_intent",
    ]
    for fn in required:
        assert fn in src, f"bot_crm.py missing: {fn}"


# ─────────────────────────────────────────────────────────────────────────────
# T44: CRM store module (source inspection)
# ─────────────────────────────────────────────────────────────────────────────

def test_crm_store_functions_source():
    """T44: store_crm.py defines required CRUD functions."""
    src = (_src / "core" / "store_crm.py").read_text(encoding="utf-8")
    required = [
        "def create_contact", "def get_contact", "def update_contact",
        "def delete_contact", "def list_contacts", "def search_contacts",
        "def add_interaction", "def list_interactions",
        "def create_task", "def list_tasks", "def complete_task",
        "def create_campaign", "def get_campaign", "def list_campaigns",
        "def add_campaign_contact", "def list_campaign_contacts",
        "def update_campaign_status", "def get_stats",
    ]
    for fn in required:
        assert fn in src, f"store_crm.py missing: {fn}"


# ─────────────────────────────────────────────────────────────────────────────
# T45: CRM intent classifier (source inspection)
# ─────────────────────────────────────────────────────────────────────────────

def test_crm_intents_defined_source():
    """T45: CRM_INTENTS contains expected intents in source."""
    src = (_src / "features" / "bot_crm.py").read_text(encoding="utf-8")
    for intent in ("add_contact", "search", "list", "campaign", "task", "stats", "unknown"):
        assert f'"{intent}"' in src, f"Missing intent: {intent}"


# ─────────────────────────────────────────────────────────────────────────────
# T46: i18n keys for N8N/CRM
# ─────────────────────────────────────────────────────────────────────────────

def test_i18n_n8n_crm_keys():
    """T46: All N8N/CRM i18n keys present in all languages."""
    strings_path = _src / "strings.json"
    with open(strings_path, encoding="utf-8") as f:
        strings = json.load(f)

    required_keys = [
        "admin_btn_n8n", "admin_btn_crm",
        "admin_n8n_title", "admin_n8n_status_ok", "admin_n8n_status_err",
        "admin_n8n_not_configured", "admin_n8n_workflows",
        "crm_title", "crm_not_available", "crm_contacts_count",
        "crm_btn_contacts", "crm_btn_add_contact", "crm_btn_search",
        "crm_contact_added", "crm_search_results", "crm_search_empty",
        "crm_enter_name", "crm_enter_search",
    ]

    for lang in ["ru", "en", "de"]:
        assert lang in strings, f"Language '{lang}' missing"
        for key in required_keys:
            assert key in strings[lang], f"Key '{key}' missing in '{lang}'"
            assert strings[lang][key], f"Key '{key}' is empty in '{lang}'"


# ─────────────────────────────────────────────────────────────────────────────
# T47: Webhook route in bot_web.py
# ─────────────────────────────────────────────────────────────────────────────

def test_webhook_route_source():
    """T47: bot_web.py defines /api/n8n/callback route."""
    src = (_src / "bot_web.py").read_text(encoding="utf-8")
    assert '/api/n8n/callback' in src, "Missing N8N webhook route"
    assert '/api/crm/contacts' in src, "Missing CRM contacts route"
    assert '/api/crm/stats' in src, "Missing CRM stats route"


# ─────────────────────────────────────────────────────────────────────────────
# T48: Admin menu has N8N/CRM buttons
# ─────────────────────────────────────────────────────────────────────────────

def test_admin_n8n_crm_buttons_source():
    """T48: Admin keyboard includes N8N and CRM buttons."""
    src = (_src / "telegram" / "bot_admin.py").read_text(encoding="utf-8")
    assert 'admin_n8n_menu' in src, "Missing N8N button in admin"
    assert 'admin_crm_menu' in src, "Missing CRM button in admin"
    assert 'def _handle_admin_n8n_menu' in src, "Missing N8N handler"
    assert 'def _handle_admin_crm_menu' in src, "Missing CRM handler"


# ─────────────────────────────────────────────────────────────────────────────
# T49: Callback routing in telegram_menu_bot.py
# ─────────────────────────────────────────────────────────────────────────────

def test_callback_routing_source():
    """T49: telegram_menu_bot.py routes N8N/CRM callbacks."""
    src = (_src / "telegram_menu_bot.py").read_text(encoding="utf-8")
    assert '"admin_n8n_menu"' in src, "Missing admin_n8n_menu callback route"
    assert '"admin_crm_menu"' in src, "Missing admin_crm_menu callback route"
    assert '"crm_contacts"' in src, "Missing crm_contacts callback route"
    assert '"crm_add_start"' in src, "Missing crm_add_start callback route"
    assert '"crm_search_start"' in src, "Missing crm_search_start callback route"


# ─────────────────────────────────────────────────────────────────────────────
# Runtime tests (only when bot_config importable — i.e. on target with bot.env)
# ─────────────────────────────────────────────────────────────────────────────

if _HAS_BOT_CONFIG:
    def test_n8n_config_runtime():
        """N8N config constants importable at runtime."""
        from core.bot_config import N8N_URL, N8N_API_KEY, N8N_TIMEOUT
        assert isinstance(N8N_URL, str)
        assert isinstance(N8N_TIMEOUT, int)

    def test_crm_config_runtime():
        """CRM config constants importable at runtime."""
        from core.bot_config import CRM_ENABLED, CRM_PG_DSN
        assert isinstance(CRM_ENABLED, bool)
        assert isinstance(CRM_PG_DSN, str)


if __name__ == "__main__":
    tests = [
        ("T40 n8n_config_source", test_n8n_config_constants_source),
        ("T41 crm_config_source", test_crm_config_constants_source),
        ("T42 n8n_adapter_source", test_n8n_adapter_functions_source),
        ("T43 crm_module_source", test_crm_module_functions_source),
        ("T44 crm_store_source", test_crm_store_functions_source),
        ("T45 crm_intents_source", test_crm_intents_defined_source),
        ("T46 i18n_keys", test_i18n_n8n_crm_keys),
        ("T47 webhook_route", test_webhook_route_source),
        ("T48 admin_buttons", test_admin_n8n_crm_buttons_source),
        ("T49 callback_routing", test_callback_routing_source),
    ]

    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
            passed += 1
        except Exception as e:
            print(f"FAIL  {name}: {e}")
            failed += 1

    if _HAS_BOT_CONFIG:
        for name, fn in [("runtime_n8n", test_n8n_config_runtime),
                         ("runtime_crm", test_crm_config_runtime)]:
            try:
                fn()
                print(f"PASS  {name}")
                passed += 1
            except Exception as e:
                print(f"FAIL  {name}: {e}")
                failed += 1
    else:
        print("SKIP  runtime tests (no bot.env / BOT_TOKEN)")

    print(f"\n{passed}/{passed+failed} passed, {failed} failed")
