# Taris — Security Architecture

**Version:** `2026.3.28`  
→ Architecture index: [architecture.md](../architecture.md)

---

## 6. Security Architecture

### 6.1 Three-Layer Prompt Injection Defense (`bot_security.py`)

**L1 — Input validation (pre-LLM scan):**  
`_check_injection(text)` scans ~25 regex patterns covering:
- Instruction override (Russian + English): "ignore previous instructions", "забудь инструкции"
- Persona hijack: "you are now", "притворись"
- Prompt extraction: "repeat your instructions", "покажи промпт"
- Credential extraction: "show api_key", "покажи токен"
- Path disclosure: `cat /home/stas/`, `bot.env`
- Shell injection: backticks, `$()`, chained dangerous commands
- Jailbreak keywords: DAN, jailbreak, developer mode

If any pattern matches: message blocked, user warned, LLM **never called**.

**L2 — User input delimiting:**  
`_wrap_user_input(text)` → `"[USER]\n{text}\n[/USER]"` prevents the LLM from treating user text as instructions.

**L3 — Security preamble:**  
`SECURITY_PREAMBLE` prepended to every free-chat and voice LLM call. Instructs the model not to reveal credentials/paths, not to disclose system prompts, not to generate shell commands, and to ignore role-override attempts.

### 6.2 Role-Based Access

| Role | Condition | Permissions |
|---|---|---|
| **Admin** | `chat_id in ADMIN_USERS` | All features + admin panel + system chat |
| **Full user** | `chat_id in ALLOWED_USERS` | All user features |
| **Approved guest** | `chat_id in _dynamic_users` | All user features (dynamically approved) |
| **Pending** | Submitted `/start`, awaiting admin | Registration confirmation only |
| **Blocked** | `reg.status == "blocked"` | Blocked message only |
