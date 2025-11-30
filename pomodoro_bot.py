from __future__ import annotations

import os
import asyncio
import logging
import random
import uuid
import functools
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, button
from discord import FFmpegOpusAudio
from gtts import gTTS
from discord.utils import get
from dotenv import load_dotenv  

# -------- asyncio.to_thread compatibility (Python 3.8+) --------
try:
    to_thread = asyncio.to_thread  # Python 3.9+
except AttributeError:  # Python 3.8 fallback
    async def to_thread(func, /, *args, **kwargs):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            functools.partial(func, *args, **kwargs),
        )


load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger("pomodoro-bot")


# -----------------------------
# Motivational quotes
# -----------------------------
MOTIVATIONAL_QUOTES = [
    # Original ones
    "Stay focused – your future self is watching.",
    "One session at a time. Just show up.",
    "Deep work now, flex later.",
    "Discipline beats motivation. You got this.",
    "Tiny consistent steps beat massive random sprints.",
    "If it matters, you’ll push through this session.",
    "The gap between average and great is this focus block.",

    # New, tougher HWPO-style lines
    "You’re not tired, you’re just used to quitting early.",
    "Your dreams called. They said, ‘Quit scrolling and start working.’",
    "You don’t need more time, you need more focus.",
    "This session won’t kill you, but your excuses might kill your goals.",
    "You say you want it. Prove it for the next 25 minutes.",
    "If you can binge nonsense for hours, you can focus for one block.",
    "Stop negotiating with your laziness and hit start.",
    "Someone out there is doing the work you’re avoiding.",
    "You’re not behind; you’re just one focused session away from catching up.",
    "You don’t need motivation, you need a timer and no way out.",
    "Your future self either thanks you or roasts you. You’re choosing right now.",
    "Hard Work Pays Off — but only if you actually work.",
    "You’re scared of being average but acting like it’s your full-time job.",
    "Your goals are allergic to TikTok. Stay here and grind.",
    "If you’re waiting to ‘feel ready’, enjoy waiting forever.",
    "You’ve failed zero sessions you actually started. Press start.",
    "Comfort is cute, but greatness is ugly, tired, and focused.",
    "You’re not stuck; you’re just pausing more than you’re working.",
    "Every focused block is you punching procrastination in the face.",
    "You don’t need a new system. You need to sit down and shut up for 25 minutes.",
    "You either suffer the pain of focus now or the pain of regret later.",
    "Your competition is studying right now. You’re deciding if you join them.",
    "You're not studying? Okay, stay like that  maybe you enjoy being poor.",
    "If you don’t want to study, no problem… you’ll just end up marrying a guy who drains your soul.",
    "Don’t study, it’s fine. How will you ever afford even a Nissan Sunny anyway?",
]

IN_SESSION_ROLE_NAME = "In Session"
AUTO_REPOST_SECONDS = 600          # 10 minutes -> send a fresh dashboard message
DASHBOARD_UPDATE_INTERVAL = 30     # edit dashboard about every 30s when > 60s left


class Phase(Enum):
    FOCUS = auto()
    SHORT_BREAK = auto()
    LONG_BREAK = auto()
    DONE = auto()


@dataclass
class PomodoroConfig:
    sessions: int = 4
    focus_minutes: int = 25
    short_break_minutes: int = 5
    long_break_minutes: int = 15
    long_break_after: int = 4


class PomodoroSession:
    """
    Represents a single user's Pomodoro run.
    Handles state, timer, voice announcements, dashboard updates, and participants.
    """

    def __init__(
        self,
        bot: commands.Bot,
        interaction: discord.Interaction,
        voice_client: discord.VoiceClient,
        config: PomodoroConfig,
    ) -> None:
        self.bot = bot
        self.interaction = interaction
        self.voice_client = voice_client
        self.config = config

        self.current_session_index: int = 0
        self.phase: Phase = Phase.FOCUS
        self.remaining_seconds: int = 0

        self.is_paused: bool = False
        self.stopped: bool = False

        self.dashboard_message: Optional[discord.Message] = None
        self.view: Optional[PomodoroView] = None  # assigned in start()
        self.task: Optional[asyncio.Task] = None

        # For rate-limited, time-based dashboard updates
        self._last_dash_update: float = 0.0

        # For automatic reposting and mentions
        self._last_auto_repost: float = 0.0
        self.text_channel = interaction.channel

        # Track participants (for the role)
        self.participant_ids: set[int] = set()

    # ----------------- basic properties / helpers -----------------

    @property
    def user(self) -> discord.User | discord.Member:
        return self.interaction.user

    def adjust_time(self, delta_seconds: int) -> None:
        """Adjust remaining time by delta, clamped to minimum 10 seconds."""
        if self.phase == Phase.DONE:
            return
        self.remaining_seconds = max(10, self.remaining_seconds + delta_seconds)

    def toggle_pause(self) -> None:
        if self.phase != Phase.DONE:
            self.is_paused = not self.is_paused

    def stop(self) -> None:
        self.stopped = True

    def _format_time(self) -> str:
        m, s = divmod(max(self.remaining_seconds, 0), 60)
        return f"{m:02d}:{s:02d}"

    def _random_quote(self) -> str:
        return random.choice(MOTIVATIONAL_QUOTES)

    # ----------------- TTS helpers -----------------

    async def _create_tts_file(self, text: str) -> str:
        """
        Generate a temporary TTS audio file asynchronously using gTTS.
        """
        os.makedirs("tts_cache", exist_ok=True)
        filename = os.path.join("tts_cache", f"{uuid.uuid4().hex}.mp3")

        def _generate():
            tts = gTTS(text=text, lang="en")
            tts.save(filename)

        # offload blocking gTTS to a thread
        await to_thread(_generate)
        return filename

    async def _play_tts(self, text: str) -> None:
        """
        Create and play a short TTS clip in the connected voice channel.
        Uses FFmpegOpusAudio so we don't need a local libopus.
        """
        if not self.voice_client or not self.voice_client.is_connected():
            return

        try:
            filepath = await self._create_tts_file(text)
        except Exception as e:
            logger.warning("Failed to generate TTS: %s", e)
            return

        # Stop anything currently playing
        if self.voice_client.is_playing():
            self.voice_client.stop()

        async def _play():
            def _after_play(error: Exception | None) -> None:
                # This callback runs in a different thread context.
                try:
                    if os.path.exists(filepath):
                        os.remove(filepath)
                except Exception as e:
                    logger.warning("Failed to delete TTS file: %s", e)
                if error:
                    logger.error("Error during audio playback: %s", error)

            try:
                # Let ffmpeg produce opus audio; no local libopus needed
                source = await FFmpegOpusAudio.from_probe(filepath)
                self.voice_client.play(source, after=_after_play)
            except Exception as e:
                logger.error("Failed to play TTS: %s", e)
                try:
                    if os.path.exists(filepath):
                        os.remove(filepath)
                except Exception:
                    pass

        # Run the FFmpegOpusAudio.from_probe async work
        await _play()

    # ----------------- Role / participants helpers -----------------

    async def _get_or_create_role(self) -> Optional[discord.Role]:
        guild = self.interaction.guild
        if guild is None:
            return None

        role = get(guild.roles, name=IN_SESSION_ROLE_NAME)
        if role is None:
            try:
                role = await guild.create_role(
                    name=IN_SESSION_ROLE_NAME,
                    mentionable=True,
                    reason="HWPO Pomodoro session role",
                )
            except discord.Forbidden:
                logger.warning("Missing permissions to create role in guild %s", guild.id)
                return None
        return role

    async def add_participant(self, member: discord.Member) -> None:
        role = await self._get_or_create_role()
        if role is None:
            return
        try:
            await member.add_roles(role, reason="Joined Pomodoro session")
            self.participant_ids.add(member.id)
        except discord.Forbidden:
            logger.warning("Missing permission to add role to %s", member.id)

    async def remove_participant(self, member: discord.Member) -> None:
        guild = member.guild
        role = get(guild.roles, name=IN_SESSION_ROLE_NAME)
        if role is None:
            return
        try:
            await member.remove_roles(role, reason="Left Pomodoro session")
        except discord.Forbidden:
            logger.warning("Missing permission to remove role from %s", member.id)
        self.participant_ids.discard(member.id)

    async def clear_participants(self) -> None:
        guild = self.interaction.guild
        if guild is None or not self.participant_ids:
            return
        role = get(guild.roles, name=IN_SESSION_ROLE_NAME)
        if role is None:
            return
        members = [guild.get_member(mid) for mid in self.participant_ids]
        for m in members:
            if m is None:
                continue
            try:
                await m.remove_roles(role, reason="Pomodoro session finished")
            except discord.Forbidden:
                logger.warning("Missing permission to remove role from %s", m.id)
        self.participant_ids.clear()

    async def _mention_participants(self, message: str) -> None:
        """Mention the in-session role with a message (e.g., on break)."""
        if not self.participant_ids:
            return
        guild = self.interaction.guild
        if guild is None or self.text_channel is None:
            return
        role = await self._get_or_create_role()
        if role is None:
            return
        try:
            await self.text_channel.send(f"{role.mention} {message}")
        except discord.HTTPException as e:
            logger.warning("Failed to send break mention: %s", e)

    # ----------------- Dashboard / Embed -----------------

    async def _build_embed(self) -> discord.Embed:
        phase_name = {
            Phase.FOCUS: "Focus",
            Phase.SHORT_BREAK: "Short Break",
            Phase.LONG_BREAK: "Long Break",
            Phase.DONE: "Completed ✅",
        }[self.phase]

        color = {
            Phase.FOCUS: discord.Color.green(),
            Phase.SHORT_BREAK: discord.Color.blurple(),
            Phase.LONG_BREAK: discord.Color.orange(),
            Phase.DONE: discord.Color.gold(),
        }[self.phase]

        embed = discord.Embed(
            title="⏱️ Pomodoro Dashboard",
            color=color,
        )

        if self.phase != Phase.DONE:
            embed.add_field(name="Status", value=phase_name, inline=True)
            embed.add_field(
                name="Session",
                value=f"{self.current_session_index}/{self.config.sessions}",
                inline=True,
            )
            embed.add_field(
                name="Time Remaining",
                value=f"`{self._format_time()}`",
                inline=False,
            )
        else:
            embed.description = "All Pomodoro sessions completed! 🎉"

        embed.add_field(
            name="Quote",
            value=self._random_quote(),
            inline=False,
        )

        embed.set_footer(text=f"Controlled by {self.user.display_name}")
        return embed

    async def update_dashboard(self, force: bool = False) -> None:
        """
        Edit the dashboard message with current state.
        """
        if not self.dashboard_message:
            return
        try:
            embed = await self._build_embed()
            await self.dashboard_message.edit(embed=embed, view=self.view)
        except discord.HTTPException as e:
            logger.warning("Failed to update dashboard: %s", e)

    async def _maybe_update_dashboard(self, force: bool = False) -> None:
        """
        Update the dashboard at most every N seconds, or more often near the end.
        """
        if not self.dashboard_message:
            return

        now = asyncio.get_running_loop().time()

        # Always update if forced, or if < 60s left, or if it's been >= interval
        if (
            force
            or self.remaining_seconds <= 60
            or now - self._last_dash_update >= DASHBOARD_UPDATE_INTERVAL
        ):
            self._last_dash_update = now
            await self.update_dashboard()

    async def _maybe_auto_repost_dashboard(self) -> None:
        """
        Every AUTO_REPOST_SECONDS, send a fresh dashboard message to the channel
        so it appears at the bottom of chat.
        """
        if self.text_channel is None:
            return
        now = asyncio.get_running_loop().time()
        if now - self._last_auto_repost < AUTO_REPOST_SECONDS:
            return
        self._last_auto_repost = now

        if self.view is None:
            self.view = PomodoroView(self)

        embed = await self._build_embed()
        try:
            msg = await self.text_channel.send(embed=embed, view=self.view)
            self.dashboard_message = msg  # future edits target the newest one
        except discord.HTTPException as e:
            logger.warning("Failed to auto-repost dashboard: %s", e)

    # ----------------- Main lifecycle -----------------

    async def start(self) -> None:
        """
        Start the Pomodoro flow and create the dashboard message.
        """
        # Create view + initial dashboard
        self.view = PomodoroView(self)
        embed = await self._build_embed()
        # Create the persistent dashboard message in the channel where command was used
        self.dashboard_message = await self.interaction.followup.send(
            embed=embed,
            view=self.view,
            wait=True,
        )

        # Kick off background task
        self.task = asyncio.create_task(self._run())

    async def _run_phase(self, duration_minutes: int, announce_text: str) -> bool:
        """
        Run a single phase (focus / break).
        Returns False if session was manually stopped.
        """
        self.remaining_seconds = int(duration_minutes * 60)

        # Reset dashboard timer and announce
        self._last_dash_update = 0.0
        await self._play_tts(announce_text)
        await self._maybe_update_dashboard(force=True)

        # Timer loop: 1-second resolution,
        # dashboard update is time-based in _maybe_update_dashboard
        while self.remaining_seconds > 0 and not self.stopped:
            if not self.is_paused:
                self.remaining_seconds -= 1

            await self._maybe_update_dashboard()
            await self._maybe_auto_repost_dashboard()
            await asyncio.sleep(1)

        # One last forced update at end of phase (if not fully stopped)
        if not self.stopped:
            await self._maybe_update_dashboard(force=True)

        return not self.stopped

    async def _run(self) -> None:
        """
        Main Pomodoro state machine:
        Focus → Break → Focus → ... → Done
        """
        try:
            for session_idx in range(1, self.config.sessions + 1):
                if self.stopped:
                    break

                self.current_session_index = session_idx
                self.phase = Phase.FOCUS

                ok = await self._run_phase(
                    self.config.focus_minutes,
                    f"Focus session {session_idx} started for {self.config.focus_minutes} minutes.",
                )
                if not ok:
                    break

                # If this was the last session, no break after
                if session_idx == self.config.sessions:
                    continue

                # Decide break type
                is_long_break = (
                    session_idx % self.config.long_break_after == 0
                )
                if is_long_break:
                    self.phase = Phase.LONG_BREAK
                    duration = self.config.long_break_minutes
                    text = f"Long break started for {duration} minutes."
                    msg_txt = f"It's long break time! {duration} minutes. Move, hydrate, but don't vanish 👀"
                else:
                    self.phase = Phase.SHORT_BREAK
                    duration = self.config.short_break_minutes
                    text = f"Short break started for {duration} minutes."
                    msg_txt = f"Short break time! {duration} minutes. Breathe, stretch, then back to work."

                # Announce in chat & then run the break phase
                await self._mention_participants(msg_txt)
                ok = await self._run_phase(duration, text)
                if not ok:
                    break

            self.phase = Phase.DONE
            self.remaining_seconds = 0
            await self.update_dashboard(force=True)
            await self._play_tts("All Pomodoro sessions are complete. Great job.")
            await self.clear_participants()
        finally:
            # The actual disconnect and message delete are handled in cleanup()
            pass

    async def cleanup(self) -> None:
        """
        Disconnect from voice and delete the dashboard.
        Called when user presses Stop or when you want to kill session.
        """
        self.stopped = True

        # Disconnect from voice
        if self.voice_client and self.voice_client.is_connected():
            try:
                await self.voice_client.disconnect()
            except Exception:
                pass

        # Delete dashboard message
        if self.dashboard_message:
            try:
                await self.dashboard_message.delete()
            except discord.HTTPException:
                pass

        # Clear roles from participants
        await self.clear_participants()

        # Remove from bot registry in case it's still there
        try:
            self.bot.pomodoro_sessions.pop(self.user.id, None)
        except Exception:
            pass

    async def show_dashboard_message(self, channel: discord.abc.Messageable) -> None:
        """
        Create a fresh dashboard message in the given channel.
        Replaces any existing dashboard message reference.
        """
        if not self.view:
            self.view = PomodoroView(self)

        # Try to delete old dashboard (if it exists)
        if self.dashboard_message:
            try:
                await self.dashboard_message.delete()
            except discord.HTTPException:
                pass

        embed = await self._build_embed()
        self.dashboard_message = await channel.send(embed=embed, view=self.view)


class PomodoroView(View):
    """
    Interactive dashboard controls:
    ➖ 5 mins | Pause/Resume | ➕ 5 mins | Stop | Join Session
    """

    def __init__(self, session: PomodoroSession):
        # timeout=None => stays active while bot is running
        super().__init__(timeout=None)
        self.session = session

    async def _ensure_owner(self, interaction: discord.Interaction) -> bool:
        """
        Restrict controls to the user who started the session (for time/stop only).
        """
        if interaction.user.id != self.session.user.id:
            await interaction.response.send_message(
                "Only the user who started this Pomodoro can control the timer.",
                ephemeral=True,
            )
            return False
        return True

    @button(
        label="-5 mins",
        emoji="➖",
        style=discord.ButtonStyle.secondary,
        row=0,
    )
    async def minus_five(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not await self._ensure_owner(interaction):
            return
        self.session.adjust_time(-5 * 60)
        await interaction.response.defer(thinking=False)
        await self.session.update_dashboard(force=True)

    @button(
        label="Pause/Resume",
        emoji="⏸️",
        style=discord.ButtonStyle.primary,
        row=0,
    )
    async def pause_resume(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not await self._ensure_owner(interaction):
            return
        self.session.toggle_pause()
        await interaction.response.defer(thinking=False)
        await self.session.update_dashboard(force=True)

    @button(
        label="+5 mins",
        emoji="➕",
        style=discord.ButtonStyle.secondary,
        row=0,
    )
    async def plus_five(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not await self._ensure_owner(interaction):
            return
        self.session.adjust_time(5 * 60)
        await interaction.response.defer(thinking=False)
        await self.session.update_dashboard(force=True)

    @button(
        label="Stop",
        emoji="🛑",
        style=discord.ButtonStyle.danger,
        row=0,
    )
    async def stop_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not await self._ensure_owner(interaction):
            return
        self.session.stop()
        await interaction.response.defer(thinking=False)
        await self.session.cleanup()

        # Disable all buttons visually after stopping
        for child in self.children:
            child.disabled = True
        # Update dashboard (if it still exists)
        if self.session.dashboard_message:
            try:
                await self.session.dashboard_message.edit(view=self)
            except discord.HTTPException:
                pass

    @button(
        label="Join Session",
        emoji="✅",
        style=discord.ButtonStyle.success,
        row=1,
    )
    async def join_session(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """
        Join the current session: assigns the In Session role.
        Anyone can use this, but they should be in the same voice channel.
        """
        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message(
                "This command can only be used inside a server.",
                ephemeral=True,
            )
            return

        vc = self.session.voice_client
        if not vc or not vc.channel:
            await interaction.response.send_message(
                "The session is not attached to a voice channel.",
                ephemeral=True,
            )
            return

        if not member.voice or member.voice.channel != vc.channel:
            await interaction.response.send_message(
                "Join the same voice channel as the session first, then press this button.",
                ephemeral=True,
            )
            return

        await self.session.add_participant(member)
        await interaction.response.send_message(
            "You joined this Pomodoro session. You'll be pinged on breaks! 💪",
            ephemeral=True,
        )


# -----------------------------
# Bot setup
# -----------------------------
intents = discord.Intents.default()
intents.guilds = True
intents.voice_states = True
# message_content is not required for slash commands
intents.message_content = False
intents.members = True  # needed for managing roles and on_voice_state_update

bot = commands.Bot(command_prefix="!", intents=intents)
# Track one session per user (per process)
bot.pomodoro_sessions = {}  # type: ignore


@bot.event
async def on_ready():
    logger.info("Logged in as %s (%s)", bot.user, bot.user.id)
    try:
        synced = await bot.tree.sync()
        logger.info("Synced %d slash commands.", len(synced))
    except Exception as e:
        logger.error("Failed to sync commands: %s", e)


@bot.event
async def on_voice_state_update(member, before, after):
    """
    If a member leaves the session's voice channel, drop their In Session role.
    """
    if member.guild is None:
        return

    for session in bot.pomodoro_sessions.values():
        if session.stopped or session.phase == Phase.DONE:
            continue
        vc = session.voice_client
        if not vc or not vc.channel:
            continue
        session_channel = vc.channel

        # Left the session channel (either to another channel or disconnected)
        if before.channel == session_channel and after.channel != session_channel:
            await session.remove_participant(member)


# -----------------------------
# Slash command: /start_pomo
# -----------------------------
@bot.tree.command(
    name="start_pomo",
    description="Start a Pomodoro session with optional custom durations.",
)
@app_commands.describe(
    sessions="Number of focus sessions (default 4).",
    focus_duration="Focus duration in minutes (default 25).",
    short_break="Short break duration in minutes (default 5).",
    long_break="Long break duration in minutes (default 15).",
    long_break_after="Number of sessions before a long break (default 4).",
    voice_channel="Voice channel to use (optional if you are already in one).",
)
async def start_pomo(
    interaction: discord.Interaction,
    sessions: app_commands.Range[int, 1, 16] = 4,
    focus_duration: app_commands.Range[int, 1, 120] = 25,
    short_break: app_commands.Range[int, 1, 60] = 5,
    long_break: app_commands.Range[int, 1, 60] = 15,
    long_break_after: app_commands.Range[int, 1, 16] = 4,
    voice_channel: Optional[discord.VoiceChannel] = None,
):
    """
    /start_pomo [sessions] [focus_duration] [short_break] [long_break] [long_break_after] [voice_channel]
    """

    # We'll send the dashboard as a followup, so defer first
    await interaction.response.defer(thinking=False, ephemeral=False)

    # Figure out which voice channel to join
    channel = voice_channel
    if channel is None:
        if interaction.user and getattr(interaction.user, "voice", None):
            channel = interaction.user.voice.channel
        else:
            await interaction.followup.send(
                "You must either be in a voice channel or specify one with the command.",
                ephemeral=True,
            )
            return

    # Join or move a voice client in this guild
    if not interaction.guild:
        await interaction.followup.send(
            "This command can only be used in a server (guild).",
            ephemeral=True,
        )
        return

    voice_client: Optional[discord.VoiceClient]
    if interaction.guild.voice_client:
        voice_client = interaction.guild.voice_client
        if voice_client.channel.id != channel.id:
            await voice_client.move_to(channel)
    else:
        voice_client = await channel.connect()

    config = PomodoroConfig(
        sessions=sessions,
        focus_minutes=focus_duration,
        short_break_minutes=short_break,
        long_break_minutes=long_break,
        long_break_after=long_break_after,
    )

    # Prevent multiple sessions for same user simultaneously, but clean up stale ones
    existing = bot.pomodoro_sessions.get(interaction.user.id)
    if existing is not None:
        task_done = existing.task is None or existing.task.done()
        vc_gone = not existing.voice_client or not existing.voice_client.is_connected()
        if task_done or vc_gone or existing.stopped:
            # Old session is effectively dead; remove it
            bot.pomodoro_sessions.pop(interaction.user.id, None)
        else:
            await interaction.followup.send(
                "You already have a Pomodoro session running. Stop it first before starting another.",
                ephemeral=True,
            )
            return

    # Register and start the session
    session = PomodoroSession(bot, interaction, voice_client, config)
    bot.pomodoro_sessions[interaction.user.id] = session

    await interaction.followup.send(
        f"Starting Pomodoro: {sessions} session(s) × {focus_duration} minute focus blocks.",
        ephemeral=True,
    )

    await session.start()

    # After session finishes, clean up registry
    async def _wait_for_finish():
        try:
            if session.task:
                await session.task
        except Exception as e:
            logger.error("Pomodoro session task errored: %s", e)
        finally:
            bot.pomodoro_sessions.pop(interaction.user.id, None)

    asyncio.create_task(_wait_for_finish())


# -----------------------------
# Slash command: /pomo_dashboard
# -----------------------------
@bot.tree.command(
    name="pomo_dashboard",
    description="Show the current Pomodoro dashboard again at the bottom of the channel.",
)
async def pomo_dashboard(interaction: discord.Interaction):
    """
    Anyone can use this. It finds an active session in this guild,
    preferring the caller's own session if they have one.
    """
    session = bot.pomodoro_sessions.get(interaction.user.id)

    # If caller has no active session, search for one in this guild
    if session is None or session.stopped or session.phase == Phase.DONE:
        session = None
        if interaction.guild:
            for s in bot.pomodoro_sessions.values():
                if s.stopped or s.phase == Phase.DONE:
                    continue
                if s.interaction.guild and s.interaction.guild.id == interaction.guild.id:
                    session = s
                    break

    if session is None:
        await interaction.response.send_message(
            "There is no active Pomodoro session I can show.",
            ephemeral=True,
        )
        return

    # We'll send a fresh dashboard as a followup
    await interaction.response.defer(thinking=False, ephemeral=False)

    # Ensure view exists
    if session.view is None:
        session.view = PomodoroView(session)

    # Delete old dashboard message, if any
    if session.dashboard_message:
        try:
            await session.dashboard_message.delete()
        except discord.HTTPException:
            pass

    # Create a new dashboard at the bottom
    embed = await session._build_embed()
    session.dashboard_message = await interaction.followup.send(
        embed=embed,
        view=session.view,
        wait=True,
    )


TOKEN = os.getenv("DISCORD_TOKEN")


def main():
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN environment variable is not set.")
    bot.run(TOKEN)


if __name__ == "__main__":
    main()
