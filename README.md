# HWPO Pomodoro Bot ⏱️

> **H.W.P.O.** – Hard Work Pays Off.  
> A Discord Pomodoro bot that bullies your procrastination and rewards your focus.

- 🎧 Voice announcements (gTTS + ffmpeg)
- 🧠 One main **dashboard message** (no spammy flood of messages)
- 🎛️ Interactive buttons: pause, +/- time, stop, join session
- 👥 “In Session” role with break pings
- 🔁 Full Pomodoro flow with short & long breaks
- 📌 `/pomo_dashboard` to bring the dashboard back to the bottom
- 🟢 Designed to run 24/7 on a VPS (Oracle Cloud Free Tier–friendly)

---

## 🔗 Quick Links

- [Features](#features)
- [Commands](#commands)
- [Local Setup](#local-setup)
- [Discord Bot Setup](#discord-bot-setup-developer-portal)
- [24/7 Deployment (Oracle Cloud)](#deploying-247-on-a-server-oracle-cloud-example)

---

## Features

### 🧱 Pomodoro Logic

- Classic Pomodoro structure with:
  - Configurable **number of sessions**
  - Configurable **focus duration**
  - Configurable **short** and **long breaks**
  - Long break every **N** sessions
- Handles:
  - Pause / resume
  - Manual stop
  - Clean shutdown + cleanup of voice + dashboard + roles
- Fully async using `asyncio` – no blocking `time.sleep()`.

### 🎛️ Dashboard UI (discord.ui)

When you start a Pomodoro, the bot sends **one dashboard embed** and keeps editing it instead of spamming messages.

The dashboard shows:

- **Status**: `Focus`, `Short Break`, `Long Break`, or `Completed ✅`
- **Time remaining** (mm:ss)
- **Session progress** (e.g. `2/4`)
- A random **motivational / HWPO quote**

#### Buttons

Each dashboard comes with a row of buttons:

- ➖ `-5 mins`  
  Subtract 5 minutes from the current phase (minimum time enforced).

- ⏸️ `Pause/Resume`  
  Toggle pause on the countdown.

- ➕ `+5 mins`  
  Add 5 minutes to the current phase.

- 🧑‍🤝‍🧑 `Join Session`  
  - Gives you a special **“In Session”** role.
  - Marks you as an active participant in this Pomodoro run.
  - You’ll get pinged on breaks (see below).

- 🛑 `Stop`  
  - Stops the entire Pomodoro flow.
  - Disconnects the bot from voice.
  - Cleans up the dashboard message and participant tracking.

> Only the **user who started the session** can use the time control / stop buttons.  
> Anyone can press **Join Session** to get the role and be tracked.

#### Dashboard Refresh Logic

To avoid rate limits and weird lag:

- The embed is **not** edited every second.
- The timer still ticks internally every second, but:
  - The dashboard is updated **at most every ~15 seconds**
  - It updates **more frequently** when there’s **< 60 seconds** left.
- Additionally, the bot can send **fresh dashboard messages periodically** (e.g., every 10 minutes) so the current dashboard stays near the **bottom of the channel** instead of buried at the top.

You can also manually bring it back with `/pomo_dashboard`.

---

### 👥 “In Session” Role & Break Pings

The bot uses a special role (e.g. `In Session`) to keep track of who’s grinding with you:

- When a user presses **Join Session**:
  - The bot creates the role if it doesn’t exist.
  - Assigns the role to that user.
  - Tracks them in the session’s participant list.

- On **every break start**:
  - The bot sends a message like:
    > `@In Session — Break time! Get up, stretch, drink water, but don’t vanish.`
  - So everyone in the session gets pinged.

- When the **whole Pomodoro run ends**:
  - The bot removes the session role from all tracked participants.
  - Cleans internal tracking for that run.

> You can also configure / rename the role in code if you want something more spicy than `In Session`.

---

## Commands

### `/start_pomo`

Starts a Pomodoro session and launches the dashboard & voice TTS.

**Usage (default):**

```text
/start_pomo
````

**With options:**

```text
/start_pomo sessions:4 focus_duration:25 short_break:5 long_break:15 long_break_after:4
```

**Options:**

* `sessions` – number of focus sessions (default: `4`)
* `focus_duration` – focus duration in minutes (default: `25`)
* `short_break` – short break in minutes (default: `5`)
* `long_break` – long break in minutes (default: `15`)
* `long_break_after` – number of focus sessions before a long break (default: `4`)
* `voice_channel` – optional voice channel

  * If omitted, the bot uses the **voice channel you’re currently in**.
  * If you’re **not** in voice and don’t specify it, the bot will refuse to start.

**Concurrency logic:**

* Only **one active Pomodoro per user** at a time.
* If a user tries to start another while one is active, they’ll be told to stop the first one.
* Stale sessions (crashed / disconnected voice) get auto-cleaned when a new session is requested.

---

### `/pomo_dashboard`

Brings your current Pomodoro dashboard **back to the bottom** of the channel.

* Available to **any user**, not only the original starter.
* If the user has an **active Pomodoro session**:

  * Deletes the old dashboard (if still around).
  * Sends a fresh dashboard message with live time remaining, buttons, and quote.
* If there is **no active session**:

  * Replies with a gentle message: `You don't have an active Pomodoro session.`

This is useful when the original dashboard gets buried way up in the chat.

---

## Requirements

* **Python** 3.10+ (locally you can also run 3.11+)
* A **Discord bot** (via [Discord Developer Portal](https://discord.com/developers/applications))
* `ffmpeg` installed on the machine
* Python libraries from `requirements.txt`:

```txt
discord.py[voice]>=2.3.2
gTTS>=2.5.1
python-dotenv>=1.0.1
```

---

## Local Setup

### 1. Clone the repo

```bash
git clone https://github.com/mohamedhiba/discord-pomodoro-bot.git
cd discord-pomodoro-bot
```

### 2. Create & activate a virtualenv

```bash
python3 -m venv venv
source venv/bin/activate   # Linux/macOS
# .\venv\Scripts\activate  # Windows (PowerShell)
```

### 3. Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Install ffmpeg

**macOS (Homebrew):**

```bash
brew install ffmpeg
```

**Ubuntu/Debian:**

```bash
sudo apt update
sudo apt install -y ffmpeg
```

Verify:

```bash
ffmpeg -version
```

### 5. Configure the Discord token

This project uses [`python-dotenv`](https://pypi.org/project/python-dotenv/) and reads from a local `.env` file.

Create a file named `.env` in the project root:

```env
DISCORD_TOKEN=YOUR_DISCORD_BOT_TOKEN_HERE
```

> ⚠️ **Important:**
>
> * **Do not** wrap the token in quotes or `< >`.
> * **Never commit** `.env` to git. Add it to `.gitignore`.

You can still use a plain environment variable if you prefer:

```bash
export DISCORD_TOKEN="YOUR_BOT_TOKEN_HERE"
```

The code will read `DISCORD_TOKEN` from the environment after loading `.env`.

### 6. Run the bot locally

```bash
python pomodoro_bot.py
```

You should see something like:

```text
[INFO] pomodoro-bot: Logged in as HWPO-Timer#4574 (1443775000476647516)
[INFO] pomodoro-bot: Synced 2 slash commands.
```

Then in Discord:

1. Make sure the bot is **online** in your server.
2. Join a voice channel.
3. Run `/start_pomo`.
4. Optionally run `/pomo_dashboard` to bring the dashboard back down.

---

## Discord Bot Setup (Developer Portal)

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2. Click **New Application**, give it a name (e.g. `HWPO Timer`).
3. Go to the **Bot** tab:

   * Click **Add Bot**
   * Copy the **bot token** (used in `.env` or `DISCORD_TOKEN`)
4. Under **Privileged Gateway Intents** you generally do **not** need `MESSAGE CONTENT` for this bot (we use only slash commands).
5. Under **OAuth2 → URL Generator**:

   * Scopes:

     * `bot`
     * `applications.commands`
   * Bot Permissions:

     * View Channels
     * Send Messages
     * Manage Roles (for `In Session` role)
     * Embed Links
     * Connect
     * Speak
   * Copy the generated URL, paste into your browser, and invite the bot to your server.

Slash commands (`/start_pomo`, `/pomo_dashboard`) will appear once the bot connects and syncs commands.

---

## Deploying 24/7 on a Server (Oracle Cloud example)

This bot is perfect for running 24/7 on a small VPS like **Oracle Cloud Free Tier**.

### 1. Create an Ubuntu VM

Set up an Ubuntu instance (e.g. 1 OCPU, 1 GB RAM is enough for this bot).

### 2. SSH into the VM

```bash
ssh -i /path/to/your_key.pem ubuntu@YOUR_ORACLE_IP
```

### 3. Install system dependencies

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip ffmpeg git
```

### 4. Clone the repo and set up venv

```bash
cd ~
git clone https://github.com/mohamedhiba/discord-pomodoro-bot.git
cd discord-pomodoro-bot

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create your `.env` on the VM:

```bash
nano .env
```

```env
DISCORD_TOKEN=YOUR_DISCORD_BOT_TOKEN_HERE
```

### 5. Create a systemd service

```bash
sudo nano /etc/systemd/system/pomodoro-bot.service
```

Paste:

```ini
[Unit]
Description=Discord Pomodoro Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/discord-pomodoro-bot
ExecStart=/home/ubuntu/discord-pomodoro-bot/venv/bin/python /home/ubuntu/discord-pomodoro-bot/pomodoro_bot.py
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

> Note: the bot reads `DISCORD_TOKEN` from `.env` in `WorkingDirectory`, so you don’t have to hardcode the token in systemd.

### 6. Enable and start the service

```bash
sudo systemctl daemon-reload
sudo systemctl enable pomodoro-bot
sudo systemctl start pomodoro-bot
sudo systemctl status pomodoro-bot
```

Watch logs:

```bash
journalctl -u pomodoro-bot -f
```

Once you see:

```text
Logged in as HWPO-Timer#4574 (...)
Synced 2 slash commands.
```

…your bot is officially running 24/7 and will auto-restart on reboot or crashes.

---

HWPO. Set the timer, join the session, and let future-you flex on everyone who quit at 14 minutes.
