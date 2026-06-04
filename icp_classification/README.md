# 🎯 Zenskar ICP Classification Agent

A Slack bot (+ CLI) that instantly classifies companies against Zenskar's ICP from just an email address or LinkedIn URL.

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure API keys
Copy `.env.example` to `.env` and fill in your keys:
```bash
cp .env.example .env
```

Keys needed:
| Key | Where to get it |
|---|---|
| `APOLLO_API_KEY` | [Apollo Settings → Integrations → API](https://app.apollo.io/#/settings/integrations/api_keys) |
| `GROQ_API_KEY` | [Groq Console → API Keys](https://console.groq.com/keys) |
| `APIFY_API_TOKEN` | [Apify Console → Settings → Integrations](https://console.apify.com/account/integrations) |
| `SLACK_BOT_TOKEN` | See Slack App Setup below |
| `SLACK_APP_TOKEN` | See Slack App Setup below |

### 3. Try CLI mode (no Slack setup needed)
```bash
python main.py --cli john@stripe.com
python main.py --cli john@acme.com jane@startup.io
python main.py --cli --file attendees.txt
```

### 4. Set up Slack Bot

1. Go to **[api.slack.com/apps](https://api.slack.com/apps)** → Create New App → From Scratch
2. Name it `ICP Classifier` and select your workspace
3. **Socket Mode**: Settings → Socket Mode → Enable → Generate an app-level token with `connections:write` scope → copy the `xapp-...` token → put it in `.env` as `SLACK_APP_TOKEN`
4. **Bot permissions**: OAuth & Permissions → Bot Token Scopes → Add:
   - `app_mentions:read`
   - `chat:write`
   - `im:history`
   - `im:read`
   - `im:write`
5. **Event subscriptions**: Event Subscriptions → Enable → Subscribe to bot events:
   - `app_mention`
   - `message.im`
6. **Install**: Install App → Install to Workspace → Copy the `xoxb-...` token → put it in `.env` as `SLACK_BOT_TOKEN`
7. **Enable DMs**: App Home → Show Tabs → Check "Allow users to send Slash commands and messages from the messages tab"
8. **Run the bot**:
```bash
python main.py
```

### 5. Using the Bot

**DM the bot** or **@mention it** in a channel:
```
john@acme.com
```
```
john@acme.com, jane@startup.io, bob@cloud.co
```
```
https://linkedin.com/in/john-doe
```

## Deploy to Railway

1. Push code to a Git repo
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Add environment variables (from `.env`)
4. Set start command: `python main.py`
5. Deploy — bot stays online 24/7

## How It Works

1. **Input**: Email or LinkedIn URL
2. **Enrichment**: Apollo.io (company data from email domain) or Apify (LinkedIn scraping)
3. **Classification**: Groq LLM (GPT OSS 120B) scores across 5 dimensions against Zenskar's ICP
4. **Output**: ICP fit verdict with score and reasoning

### Scoring Dimensions
| Dimension | Weight | What it checks |
|---|---|---|
| Company Size | 25% | Employee count as proxy for ARR |
| Industry | 25% | B2B SaaS/Cloud/API vs other |
| Geography | 15% | US/UK/India/Australia |
| Finance Persona | 20% | Has CFO/Controller/VP Finance? |
| Pricing Complexity | 15% | Usage-based/hybrid pricing signals |

### Verdicts
- ✅ **Strong ICP Fit** (≥7.5/10)
- ⚠️ **Partial Fit** (5.5-7.4)
- 🟡 **Weak Fit** (3.5-5.4)
- ❌ **Not ICP** (<3.5 or disqualified)
# Zenskar-ICP-Classification
