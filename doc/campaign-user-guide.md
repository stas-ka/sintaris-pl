# Taris Campaign Agent — User Guide

**Version:** 1.0 · **Date:** 2026-04-13  
**Audience:** Advanced users — familiar with Taris, N8N, and Google Sheets  
**Topic:** How to run an AI-powered email campaign to a selected group of clients  

---

## 1. What Is the Campaign Agent?

The **Campaign Agent** is an automated workflow built into Taris that lets you send a personalised email to a selected group of clients — all from your Telegram chat. You describe what the message is about, and the system:

1. Reads your client list from a **Google Sheet**
2. Uses **AI (OpenAI GPT-4o-mini)** to select the best-matching clients and write a personalised email template
3. Shows you a **preview** so you can review and edit before sending
4. Sends the emails via **Gmail** and logs the results back to the Google Sheet

No programming or technical skills are needed to run a campaign — just your Telegram app and a prepared Google Sheet.

---

## 2. System Overview

The diagram below shows how the components work together:

![Architecture Overview](campaign-architecture.drawio)

> **How to view the diagram:** Open `campaign-architecture.drawio` in [draw.io](https://app.diagrams.net/) (free, browser-based) or import it into Google Drive / Confluence.

### Components at a glance

| Component | What it does |
|---|---|
| **Taris (Telegram Bot)** | Your control panel — you interact with it in Telegram to start and approve campaigns |
| **N8N** | Automation engine that orchestrates the workflow (reads the sheet, calls AI, sends emails) |
| **Google Sheets** | Your client database and campaign log |
| **OpenAI GPT-4o-mini** | AI model that selects matching clients and generates a personalised email template |
| **Gmail** | Email delivery service used to send the campaign messages |

---

## 3. Prerequisites

Before running a campaign, make sure:

| # | Requirement | Who sets it up |
|---|---|---|
| 1 | You have access to the **Taris Telegram bot** and are an authorised user | Administrator |
| 2 | The **Google Sheet** with your client list is set up (see §4 below) | You |
| 3 | N8N has been configured with the campaign webhook and Google/Gmail credentials | Administrator |
| 4 | The variables `N8N_CAMPAIGN_SELECT_WH`, `N8N_CAMPAIGN_SEND_WH`, and `CAMPAIGN_SHEET_ID` are set in `bot.env` | Administrator |

> **For administrators:** Configuration details are in `doc/howto_admin.md`. If any variable is missing, the bot will show:  
> _"⚠️ Campaign agent not configured. Set N8N\_CAMPAIGN\_SELECT\_WH and N8N\_CAMPAIGN\_SEND\_WH in bot.env."_

---

## 4. Preparing the Google Sheet

The Google Sheet is the source of truth for your client data. You manage it directly — Taris and N8N read from it automatically.

### 4.1 Required Sheet Structure

Your Google Sheet must contain **three tabs** (exact names matter):

#### Tab 1 — `Клиенты` (Clients)

This is your client database. Each row is one client.

| Column | Description | Example |
|---|---|---|
| `Имя` / `ФИО` | Client name (first and last name) | Анна Иванова |
| `Email` / `Почта` | Email address (required for sending) | anna@example.com |
| `Телефон` | Phone number (optional) | +49 171 1234567 |
| `Тип` | Client category or VIP status | VIP / Regular |
| `Интересы` | Topics the client is interested in | здоровье, спорт |
| `Компания` | Company name (optional) | Sintaris GmbH |
| `Доп. инфо` | Any additional details used by AI for matching | Куплен курс по питанию |

> **Tips:**
> - The column names can be in Russian or English — N8N maps them automatically
> - Keep email addresses clean (no spaces, no typos) — invalid addresses will fail silently
> - The more detail in "Интересы" and "Доп. инфо", the better the AI can match clients to your campaign topic

#### Tab 2 — `Шаблоны` (Templates) — *optional*

If you want to provide your own base templates for specific event types, add them here. N8N will use these as a starting point before AI customisation. Leave this tab empty if you want the AI to generate the template from scratch.

| Column | Description |
|---|---|
| `Тема` | Template topic (e.g. "Вебинар", "Акция") |
| `Текст` | Base email body text |

#### Tab 3 — `Статус рассылок` (Campaign Status)

This tab is **written by N8N automatically** after each campaign send. You can read it to track results.

| Column | Description |
|---|---|
| `Дата` | Date and time of the campaign |
| `Тема` | Campaign topic you entered |
| `Клиент` | Recipient name |
| `Email` | Recipient email |
| `Статус` | `sent` / `failed` |
| `Ошибка` | Error details (if failed) |

### 4.2 Sharing the Sheet with N8N

1. Open your Google Sheet
2. Click **Share** → Add the N8N Google service account email as **Editor**
3. The service account email is shown in N8N under **Settings → Credentials → Google Sheets Account 3**

> **Important:** If you get the error _"Google credential expired"_, the N8N administrator needs to reconnect the Google credential (see §7 — Troubleshooting).

---

## 5. Running a Campaign — Step by Step

### Step 1 — Open the Agents Menu

In Telegram, open your Taris bot and navigate to:

```
Main Menu → 🤖 Agents → 📧 Client Campaign
```

The bot will prompt you to enter a campaign topic.

---

### Step 2 — Enter the Campaign Topic

Type a short description of what your message is about. This is what the AI uses to select the right clients and write the email.

**Examples:**
- `Invitation to LR Product Webinar`
- `New Year's health programme offer`
- `Thank you message for VIP clients — December`
- `Seminar on AI tools for small businesses`

> **Tip:** Be specific. The AI reads each client's interests and matches them to your topic. "Webinar" alone is too vague; "Webinar on nutrition for active lifestyle" gives much better results.

---

### Step 3 — Enter Client Filters (Optional)

The bot then asks for optional filters to narrow down the recipient list.

**Examples:**
- `type: VIP, interests: health`
- `company: Sintaris GmbH`
- `language: German`
- Send **`-`** (a dash) to skip and target all clients who match the topic

> **Note:** Filters are passed to the AI alongside the topic. Even without filters, the AI will only include clients whose interests match your campaign topic.

---

### Step 4 — Wait for AI Selection (~10–30 seconds)

The bot displays:  
_"⏳ Selecting clients via N8N… (may take up to 30 sec)"_

During this time:
1. N8N reads the `Клиенты` tab from your Google Sheet
2. OpenAI GPT-4o-mini reviews each client's profile against your topic and filters
3. The AI generates a personalised email template
4. N8N returns the selected clients and template to Taris

> **If no clients are found:** The bot will say _"No matching clients found for this topic."_ — review your topic/filters and try again, or add more clients to the sheet.

---

### Step 5 — Review the Preview

The bot displays a preview card showing:

```
📋 Campaign Preview

👥 Selected clients: 12
Anna Ivanova, Peter Müller, Maria Garcia, … (+9)

📝 Email template:
Dear {name},

We invite you to our webinar on "AI tools for 
your business" on April 20th at 18:00 CET.
...
```

You have three options:

| Button | Action |
|---|---|
| **✅ Send Campaign** | Approve and send immediately |
| **✏️ Edit Template** | Modify the email text before sending |
| **❌ Cancel** | Cancel the campaign |

---

### Step 6 — Edit the Template (Optional)

If you tap **✏️ Edit Template**, the bot shows you the current template and asks you to send a new version.

You can use these **placeholders** in the template text — they are replaced with each client's actual data when the email is sent:

| Placeholder | Replaced with |
|---|---|
| `{name}` | Client's name (from the `Имя` column) |
| `{company}` | Client's company name |
| `{interests}` | Client's listed interests |

**Example template:**

```
Hello {name},

We're excited to invite you to our upcoming webinar 
on health and wellbeing. Given your interest in {interests}, 
we think you'll find it very valuable.

Date: April 20, 2026 · 18:00 CET
Register: https://sintaris.net/webinar

Best regards,
The Sintaris Team
```

After sending the new template, you'll see the updated preview. Tap **✅ Send Campaign** when ready.

---

### Step 7 — Confirm and Send

Tap **✅ Send Campaign** to start sending.

The bot displays:  
_"📤 Sending campaign… Please wait."_

N8N sends emails one by one via Gmail and logs each result to the `Статус рассылок` tab.

---

### Step 8 — Receive the Result

When complete, the bot shows:

```
✅ Campaign completed!

📤 Sent: 12 emails

📊 Campaign Status in Google Sheets → [link]
```

Click the link to open the `Статус рассылок` tab and see which emails were delivered and which (if any) failed.

---

## 6. Campaign Flow — Quick Reference

```
You (Telegram)              Taris Bot               N8N                Google / AI / Gmail
──────────────              ─────────               ───                ───────────────────
📧 Open Agent menu   →     Show topic prompt
Enter topic          →     Store topic
Enter filters        →     Trigger N8N select  →   Read Клиенты tab  →  AI selects clients
                    ←     Show preview        ←   Return clients + template
Review preview
  [Edit template]   →     Ask for new text
  Send new text     →     Show updated preview
  [Send Campaign]   →     Trigger N8N send    →   Send via Gmail    →  Gmail delivers emails
                                               →   Log to Статус     →  Sheet updated
                    ←     Show result         ←   Return sent count
Open status link    ←     View sheet
```

---

## 7. Troubleshooting

| Problem | What to do |
|---|---|
| _"Campaign agent not configured"_ | Ask your administrator to set the N8N webhook URLs in `bot.env` |
| _"No matching clients found"_ | Make the topic more general, or remove filters, or add more clients to the sheet |
| _"Google credential expired"_ | Ask your administrator to reconnect **Google Sheets Account 3** in N8N (N8N → Settings → Credentials) |
| _"AI service error"_ | OpenAI API may be temporarily unavailable — wait a minute and try again |
| _"Email sending error"_ | Gmail credentials may need renewal — ask your administrator |
| Emails sent but some clients missing | Check the `Статус рассылок` tab for the `Ошибка` column — invalid email addresses are the most common cause |
| Campaign takes more than 2 minutes | N8N timeout — the administrator can increase `N8N_CAMPAIGN_TIMEOUT` in `bot.env` (default: 90 seconds) |

---

## 8. Best Practices

- **Keep your client list up to date.** Remove invalid or unsubscribed email addresses from the sheet regularly.
- **Test with a small group first.** Add a `type: test` column for your test clients and use `type: test` as a filter on your first campaign.
- **Use DEMO mode for onboarding.** The administrator can enable `CAMPAIGN_DEMO_MODE=true` in `bot.env` to use hardcoded demo clients instead of the real sheet — useful for training new users.
- **Review the status tab after every campaign.** Failed deliveries may indicate outdated email addresses or Google credential issues.
- **Do not run two campaigns simultaneously.** The campaign state is per-user: if you start a new campaign while one is in progress, the previous one will be cancelled.

---

## 9. Frequently Asked Questions

**Q: Can I add more columns to the client sheet?**  
A: Yes. N8N reads all columns and passes them to the AI. Custom columns (e.g. "Last Purchase Date", "Language") help the AI make better selections.

**Q: Will clients receive personalised messages or the same template?**  
A: The template has placeholders (`{name}`, `{company}`, `{interests}`) that are filled in for each client individually before sending.

**Q: Can I schedule a campaign for a specific date and time?**  
A: Not directly from Taris — the campaign starts as soon as you confirm. For scheduled sending, ask your N8N administrator to add a time-delay node to the workflow.

**Q: How many clients can I send to in one campaign?**  
A: There is no hard limit in Taris. Practical limits depend on Gmail's daily sending quota (typically 500 emails/day for regular Gmail, 2,000/day for Google Workspace).

**Q: Where is the "Agents" menu?**  
A: Main Menu → scroll down → **🤖 Agents**. If you don't see it, you may not have the required access level — contact your administrator.

**Q: Can I cancel after clicking "Send Campaign"?**  
A: No. Once you confirm sending, N8N begins immediately. You can stop new campaigns from starting, but emails already in the queue will be delivered.

---

## 10. Admin Reference — Configuration Variables

> *This section is for administrators configuring the system, not for regular users.*

| Variable | Description | Example |
|---|---|---|
| `N8N_CAMPAIGN_SELECT_WH` | N8N webhook URL for client selection | `https://n8n.example.com/webhook/abc123` |
| `N8N_CAMPAIGN_SEND_WH` | N8N webhook URL for email sending | `https://n8n.example.com/webhook/def456` |
| `CAMPAIGN_SHEET_ID` | Google Sheet ID (from the URL) | `1jQaJZA4cBS2sLtE42zpwDHMn6grvDBAqoK_8Sp6PmXA` |
| `N8N_CAMPAIGN_TIMEOUT` | Max seconds to wait for N8N response | `90` |
| `CAMPAIGN_DEMO_MODE` | Use demo clients instead of real sheet | `true` / `false` |
| `CAMPAIGN_FROM_EMAIL` | Sender email address for all campaigns | `info@sintaris.net` |

All variables are set in `~/.taris/bot.env` on the server. Restart Taris after any change:  
```bash
systemctl --user restart taris-telegram
```

---

*For technical questions about N8N workflow setup, see `concept/taris-n8n-crm-integration.md`.*  
*For general Taris usage, see `doc/howto_bot.md`.*  
*For administrator setup, see `doc/howto_admin.md`.*
