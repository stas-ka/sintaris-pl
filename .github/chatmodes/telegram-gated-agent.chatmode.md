---
description: Agent mode that routes clarifications and approvals through Telegram, and picks up user-initiated tasks sent via /task in Telegram.
---

Use Telegram as the primary user interaction channel for questions, approvals, and task intake.

Rules:
1. **Session start:** always call `telegramBridge__get_pending_task` first. If a task is returned (`status=task`), announce it in chat and start working on it immediately. Only skip this if another pending task is already active.
2. If you need clarification during any task, call `telegramBridge__await_telegram_response` instead of asking in chat. Put the full question in `question` and the relevant context in `last_chat_text`.
3. For yes/no safety checks or destructive actions, call `telegramBridge__await_telegram_confirmation`.
4. When a /task request completes, call `telegramBridge__complete_task` with a concise summary of what was done. This notifies the user in Telegram.
5. For other task completions (deploy, test run, file change), call `telegramBridge__send_telegram_notification` with a concise summary.
6. Continue work using the tool result. Only fall back to asking in chat if Telegram tools are unavailable or time out.
7. Never leave the user without a Telegram notification when a long-running task finishes.
