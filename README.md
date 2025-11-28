# HWPO Pomodoro Bot ⏱️

A Discord Pomodoro bot with:

- 🎧 Voice announcements (using gTTS + ffmpeg)
- 🧠 A single interactive **dashboard message** (no spam)
- 🎛️ Buttons to pause, add/subtract time, and stop
- 🔁 Full Pomodoro flow with short/long breaks
- 🟢 Designed to run 24/7 on a server (e.g. Oracle Cloud Free Tier)

---

## Features

### 🧱 Pomodoro Logic

- Focus + break cycles with:
  - Configurable number of sessions
  - Configurable focus duration
  - Short and long breaks
  - Long break every _N_ sessions
- Handles pause/resume and manual stop
- Works fully asynchronously (no blocking `sleep()` on the main thread).

### 🎛️ Dashboard UI (discord.ui)

When you start a session, the bot sends a **single dashboard message** and keeps editing it instead of spamming the channel.

The embed shows:

- Current status: `Focus`, `Short Break`, `Long Break`, or `Done ✅`
- Time remaining
- Current session progress (e.g., `2/4`)
- A random motivational quote

It also has four buttons:

- ➖ `-5 mins` → subtract 5 minutes from current phase
- ⏸️ `Pause/Resume` → toggle timer pause
- ➕ `+5 mins` → add 5 minutes to current phase
- 🛑 `Stop` → end the entire Pomodoro, disconnect from VC, and delete the dashboard

Only the user who started the session can control it.

### 🔊 Voice Announcements

The bot joins a voice channel and plays short TTS clips using:

- [`gTTS`](https://pypi.org/project/gTTS/) to generate MP3
- `ffmpeg` to stream audio to Discord via `FFmpegOpusAudio`

It announces:

- Focus session start
- Short/long break start
- Final completion of all sessions

All TTS is generated on the fly and temporary files are deleted after playback.

---

## Commands

### `/start_pomo`

Start a Pomodoro session.

**Usage:**

```text
/start_pomo
````

or with options:

```text
/start_pomo sessions:4 focus_duration:25 short_break:5 long_break:15 long_break_after:4
```

**Options:**

* `sessions` – number of focus sessions (default: `4`)
* `focus_duration` – focus duration in minutes (default: `25`)
* `short_break` – short break in minutes (default: `5`)
* `long_break` – long break in minutes (default: `15`)
* `long_break_after` – number of sessions before a long break (default: `4`)
* `voice_channel` – optional voice channel to use

  * If omitted, the bot will use the voice channel you are currently in
  * If you’re not in voice and don’t specify this, the bot will refuse to start

Only **one Pomodoro** per user is allowed at a time. If a previous session died or the bot was kicked, stale sessions are auto-cleaned.

### `/test_tts` (optional)

If enabled in code, plays a simple TTS line in your current voice channel to verify TTS + ffmpeg are working.

---

## Requirements

* **Python** 3.10+
* **Discord bot** (created via the [Discord Developer Portal](https://discord.com/developers/applications))
* `ffmpeg` installed on the host machine
* Libraries from `requirements.txt`:

```txt
discord.py[voice]>=2.3.2
gTTS>=2.5.1
```

---

## Local Setup

### 1. Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/discord-pomodoro-bot.git
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

### 5. Set the Discord bot token

This project reads the token from the `DISCORD_TOKEN` environment variable.

#### macOS / Linux:

```bash
export DISCORD_TOKEN="YOUR_BOT_TOKEN_HERE"
```

#### Windows (PowerShell):

```powershell
$env:DISCORD_TOKEN="YOUR_BOT_TOKEN_HERE"
```

> ⚠️ Never commit the token. Keep it out of the code.

### 6. Run the bot

```bash
python pomodoro_bot.py
```

You should see logs like:

```text
Logged in as HWPO-Timer#1234 (ID)
Synced 1 slash commands.
```

In your Discord server:

1. Verify the bot is **online**.
2. Join a voice channel.
3. Run `/start_pomo`.

---

## Discord Bot Setup (Developer Portal)

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2. Create a **New Application** → give it a name.
3. Under **Bot**:

   * Click **Add Bot**
   * Copy the **token** (use it for `DISCORD_TOKEN`)
4. Under **OAuth2 → URL Generator**:

   * Scopes: `bot`, `applications.commands`
   * Bot Permissions:

     * View Channels
     * Send Messages
     * Embed Links
     * Connect
     * Speak
   * Copy the generated URL, paste in your browser, and add the bot to your server.

Slash commands (`/start_pomo`, `/test_tts`) will appear once the bot connects and syncs.

---

## Deploying 24/7 on a Server (Oracle Cloud example)

This bot is designed to run on a VPS (e.g., Oracle Cloud Free Tier).

**Basic outline:**

1. Create an Ubuntu VM on Oracle.

2. SSH into it:

   ```bash
   ssh -i /path/to/key.pem ubuntu@YOUR_ORACLE_IP
   ```

3. Install dependencies:

   ```bash
   sudo apt update
   sudo apt install -y python3 python3-venv python3-pip ffmpeg git
   ```

4. Clone the repo and set up venv:

   ```bash
   git clone https://github.com/YOUR_USERNAME/discord-pomodoro-bot.git
   cd discord-pomodoro-bot
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

5. Create a systemd service:

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
   Environment=DISCORD_TOKEN=YOUR_DISCORD_BOT_TOKEN_HERE

   [Install]
   WantedBy=multi-user.target
   ```

6. Enable and start:

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable pomodoro-bot
   sudo systemctl start pomodoro-bot
   sudo systemctl status pomodoro-bot
   ```

Now your Pomodoro bot runs 24/7 and restarts on reboot.

