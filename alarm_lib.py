"""Shared alarm store + trigger logic for SayAlarm."""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path

STORE_DIR = Path.home() / ".local/share/sayalarm"
STORE_FILE = STORE_DIR / "alarms.json"
SOUNDS_DIR = STORE_DIR / "sounds"  # your imported music lives here
VIDEOS_DIR = STORE_DIR / "videos"  # your 30s video clips live here
VIDEO_CLIP_SECONDS = 30

ALARM_SOUND = "/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga"
FALLBACK_SOUND = "/usr/share/sounds/freedesktop/stereo/complete.oga"
AUDIO_EXTS = {".mp3", ".ogg", ".oga", ".wav", ".m4a", ".flac", ".opus", ".wma"}
VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v"}

REPEATS = ["once", "daily", "weekdays", "weekends", "custom", "interval"]
REPEAT_LABELS = {
    "once": "Once",
    "daily": "Daily",
    "weekdays": "Mon–Fri",
    "weekends": "Sat–Sun",
    "custom": "Custom days",
    "interval": "Every X min",
}
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

CHALLENGES = ["none", "math", "type"]
CHALLENGE_LABELS = {"none": "None", "math": "🧮 Math", "type": "⌨️ Type note"}


def load_alarms() -> list[dict]:
    try:
        return json.loads(STORE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_alarms(alarms: list[dict]) -> None:
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STORE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(alarms, indent=2))
    tmp.replace(STORE_FILE)


def minute_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M")


def repeat_matches(alarm: dict, now: datetime) -> bool:
    """Does this alarm's repeat rule include today? (time match checked separately)"""
    repeat = alarm.get("repeat", "once")
    wd = now.weekday()  # Mon=0
    if repeat == "once":
        only = alarm.get("one_shot_date")  # YYYY-MM-DD or None (= today it was created)
        return only in (None, now.strftime("%Y-%m-%d"))
    if repeat == "daily":
        return True
    if repeat == "weekdays":
        return wd < 5
    if repeat == "weekends":
        return wd >= 5
    if repeat == "custom":
        return wd in alarm.get("days", [])
    if repeat == "interval":
        return interval_matches(alarm, now)
    return False


def interval_window(alarm: dict, day: datetime) -> tuple[datetime, datetime] | None:
    """(start, end) datetimes of the nag window for `day`'s date. None if off."""
    try:
        every = max(1, int(alarm.get("every_min", 60)))
        start = day.replace(hour=int(alarm.get("from_h", 9)),
                            minute=int(alarm.get("from_m", 0)),
                            second=0, microsecond=0)
        end = day.replace(hour=int(alarm.get("to_h", 21)),
                          minute=int(alarm.get("to_m", 0)),
                          second=0, microsecond=0)
    except (TypeError, ValueError):
        return None
    if end <= start or every <= 0:
        return None
    return start, end


def interval_matches(alarm: dict, now: datetime) -> bool:
    """True on each exact nag minute inside the window."""
    w = interval_window(alarm, now)
    if w is None:
        return False
    start, end = w
    if not (start <= now < end):
        return False
    every = max(1, int(alarm.get("every_min", 60)))
    elapsed = int((now - start).total_seconds() // 60)
    return elapsed % every == 0


def repeat_label(alarm: dict) -> str:
    if alarm.get("repeat") == "interval":
        return f"Every {alarm.get('every_min', 60)}min"
    return REPEAT_LABELS.get(alarm.get("repeat", "once"), "")


def is_regular_due(alarm: dict, now: datetime) -> bool:
    if not alarm.get("enabled", True):
        return False
    if alarm.get("snooze_until", 0):
        return False  # snoozed alarms fire via snooze path
    if alarm.get("last_fired_min") == minute_key(now):
        return False
    if alarm.get("repeat") == "interval":
        return interval_matches(alarm, now)
    if (alarm.get("hour"), alarm.get("min")) != (now.hour, now.minute):
        return False
    return repeat_matches(alarm, now)


def is_snooze_due(alarm: dict, now: datetime) -> bool:
    su = alarm.get("snooze_until", 0)
    if not su or not alarm.get("enabled", True):
        return False
    if now.timestamp() < su:
        return False
    return alarm.get("last_fired_min") != minute_key(now)


def next_fire_in_minutes(alarm: dict, now: datetime) -> int | None:
    """Minutes until this alarm fires next (0 = now). None if disabled/never."""
    if not alarm.get("enabled", True):
        return None
    su = alarm.get("snooze_until", 0)
    if su and su > now.timestamp():
        return max(0, int((su - now.timestamp()) // 60))
    for ahead in range(0, 8 * 24 * 60):
        cand = now + timedelta(minutes=ahead)
        if alarm.get("repeat") != "interval" and \
                (alarm.get("hour"), alarm.get("min")) != (cand.hour, cand.minute):
            continue
        if not repeat_matches(alarm, cand):
            continue
        return ahead
    return None


def fmt_countdown(ahead: int) -> str:
    if ahead < 1:
        return "firing now! 🚨"
    h, m = divmod(ahead, 60)
    d, h = divmod(h, 24)
    if d:
        return f"in {d}d {h}h"
    if h:
        return f"in {h}h {m}m"
    if m:
        return f"in {m}m"
    return "firing now! 🚨"


def next_fire_text(alarm: dict, now: datetime) -> str:
    if not alarm.get("enabled", True):
        return "off"
    if alarm.get("snooze_until", 0):
        return f"snoozed, fires {fmt_countdown(next_fire_in_minutes(alarm, now) or 0)}"
    ahead = next_fire_in_minutes(alarm, now)
    return fmt_countdown(ahead) if ahead is not None else "—"


REPEAT_COLORS = {
    "once": "#c77dff",
    "daily": "#5eb8ff",
    "weekdays": "#5eff8a",
    "interval": "#ffea00",
    "weekends": "#ffb84d",
    "custom": "#ff5e8e",
}


def speak(text: str, times: int = 3, background: bool = True) -> None:
    """Speak text aloud `times` times, then stop. Runs in a thread by default."""

    def _run():
        import time as _t
        for i in range(max(1, times)):
            try:
                subprocess.run(
                    ["espeak-ng", "-v", "en", "-s", "165", text],
                    check=False, capture_output=True, timeout=120,
                )
            except (FileNotFoundError, subprocess.SubprocessError):
                return
            if i < max(1, times) - 1:
                _t.sleep(0.8)

    if background:
        threading.Thread(target=_run, daemon=True).start()
    else:
        _run()


def play_file(path: str, timeout: int = 120) -> bool:
    """Play any audio file (mp3/ogg/wav/…). Tries mpv, then ffplay, then paplay."""
    p = Path(path)
    if not p.is_file():
        return False
    candidates = [
        (["mpv", "--no-video", "--really-quiet", str(p)], timeout),
        (["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(p)], timeout),
        (["paplay", str(p)], 60),
    ]
    for cmd, to in candidates:
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=to)
            if result.returncode == 0:
                return True
        except FileNotFoundError:
            continue  # player not installed, try next
        except subprocess.SubprocessError:
            return False
    return False


def default_sound_path() -> str:
    return ALARM_SOUND if Path(ALARM_SOUND).exists() else FALLBACK_SOUND


def player_cmd(path: str) -> list[str] | None:
    """Command that plays `path` (blocking). None if no player installed."""
    import shutil
    p = Path(path)
    if not p.is_file():
        return None
    if shutil.which("mpv"):
        return ["mpv", "--no-video", "--really-quiet", str(p)]
    if shutil.which("ffplay"):
        return ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(p)]
    if shutil.which("paplay"):
        return ["paplay", str(p)]
    return None


def preview(path: str | None) -> None:
    """Play a sound file once in the background (for the Preview button)."""
    if not path:
        path = default_sound_path()
    threading.Thread(target=play_file, args=(path,), daemon=True).start()


def play_voice_note(path: str, times: int = 2) -> None:
    """Play your recorded voice note instead of the robot voice."""

    def _run():
        import time as _t
        for i in range(max(1, times)):
            if not play_file(path, timeout=120):
                break
            if i < max(1, times) - 1:
                _t.sleep(0.6)

    threading.Thread(target=_run, daemon=True).start()


def play_sound(times: int = 2, custom: str | None = None) -> None:
    def _run():
        if custom:
            if not play_file(custom, timeout=300):
                # Custom file gone? Fall back to the default alarm.
                play_file(default_sound_path(), timeout=60)
            return
        sound = default_sound_path()
        for _ in range(times):
            if not play_file(sound, timeout=60):
                break

    threading.Thread(target=_run, daemon=True).start()


def stop_ringing(alarm_id: str) -> None:
    """Clear the ringing flag so the ringer process stops the loop."""
    alarms = load_alarms()
    for a in alarms:
        if a["id"] == alarm_id:
            a["ringing"] = False
    save_alarms(alarms)


# ------------------------------------------------- music auto-duck ---

def duck_players() -> list[str]:
    """Pause every currently-playing player. Returns their ids for resume."""
    try:
        out = subprocess.run(["playerctl", "-l"], capture_output=True,
                             text=True, timeout=10)
    except (FileNotFoundError, subprocess.SubprocessError):
        return []
    playing = []
    for pid in out.stdout.split():
        try:
            st = subprocess.run(["playerctl", "-p", pid, "status"],
                                capture_output=True, text=True, timeout=5)
            if st.stdout.strip().lower() == "playing":
                subprocess.run(["playerctl", "-p", pid, "pause"],
                               capture_output=True, timeout=5)
                playing.append(pid)
        except (FileNotFoundError, subprocess.SubprocessError):
            continue
    return playing


def unduck_players(player_ids: list[str] | None) -> None:
    for pid in player_ids or []:
        try:
            subprocess.run(["playerctl", "-p", pid, "play"],
                           capture_output=True, timeout=5)
        except (FileNotFoundError, subprocess.SubprocessError):
            continue


def unduck_alarm(alarm_id: str) -> None:
    """Resume players ducked by this alarm's firing (idempotent)."""
    alarms = load_alarms()
    for a in alarms:
        ids = a.get("ducked_players") or []
        if a["id"] == alarm_id and ids:
            unduck_players(ids)
            a["ducked_players"] = []
    save_alarms(alarms)


# ------------------------------------------------- weather briefing ---

def get_briefing(now: datetime) -> str:
    """'Good morning! It's 7 AM. Clear, 22 degrees.' (cached, offline-safe)."""
    hour = now.hour
    greet = "Good morning" if hour < 12 else \
        "Good afternoon" if hour < 18 else "Good evening"
    clock = now.strftime("%-I %p").strip()  # "7 AM"
    weather = ""
    cache = STORE_DIR / "weather.json"
    try:
        cached = json.loads(cache.read_text())
        if now.timestamp() - cached.get("ts", 0) < 1800:
            weather = cached.get("text", "")
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    if not weather:
        try:
            r = subprocess.run(
                ["curl", "-s", "--max-time", "8", "wttr.in/?format=%C+%t"],
                capture_output=True, text=True, timeout=12)
            weather = r.stdout.strip().replace("+", "").replace("°C", " degrees")
            if weather:
                STORE_DIR.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps({"ts": now.timestamp(), "text": weather}))
        except (FileNotFoundError, subprocess.SubprocessError, OSError):
            weather = ""
    parts = [f"{greet}! It's {clock}."]
    if weather:
        parts.append(f"Outside: {weather}.")
    return " ".join(parts)


# ------------------------------------------------- sunrise ramp ---

def brightness_max() -> int | None:
    try:
        r = subprocess.run(["brightnessctl", "m"], capture_output=True,
                           text=True, timeout=5)
        return int(r.stdout.strip().split("\n")[0])
    except (FileNotFoundError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def set_brightness(value: int) -> None:
    try:
        subprocess.run(["brightnessctl", "s", str(max(1, value))],
                       capture_output=True, timeout=5)
    except (FileNotFoundError, subprocess.SubprocessError):
        pass


def sunrise_start_for(alarm: dict, now: datetime) -> datetime | None:
    """When the pre-alarm glow should begin today (None if n/a)."""
    mins = int(alarm.get("sunrise_min", 0) or 0)
    if mins <= 0 or not alarm.get("enabled", True):
        return None
    if alarm.get("repeat") == "interval":
        return None
    fire = now.replace(hour=alarm.get("hour", 7), minute=alarm.get("min", 0),
                       second=0, microsecond=0)
    if fire < now:  # today's already passed (daily-style); glow for tomorrow
        fire += timedelta(days=1)
    return fire - timedelta(minutes=mins)


def import_sound(src: str) -> str | None:
    """Copy a music file into the app's sounds folder. Returns the new path."""
    import shutil
    s = Path(src)
    if not s.is_file():
        return None
    SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
    dest = SOUNDS_DIR / s.name
    n = 1
    while dest.exists():
        dest = SOUNDS_DIR / f"{s.stem}_{n}{s.suffix}"
        n += 1
    try:
        shutil.copy2(s, dest)
        return str(dest)
    except OSError:
        return None


def sound_label(alarm: dict) -> str:
    s = alarm.get("sound")
    return Path(s).name if s else "Default alarm"


def extract_beat_frames(gif_path: str, width: int = 320) -> tuple[list[str], list[int]]:
    """Split a gif into PNG frames + durations.json. Returns load_beat_frames()."""
    try:
        from PIL import Image
    except ImportError:
        return [], []
    base = Path(gif_path)
    if not base.is_file():
        return [], []
    dest = base.parent / f"{base.stem}_frames"
    try:
        im = Image.open(base)
        n = getattr(im, "n_frames", 1)
        dest.mkdir(parents=True, exist_ok=True)
        durations = []
        for i in range(n):
            im.seek(i)
            durations.append(im.info.get("duration", 90))
            frame = im.convert("RGB")
            if frame.width > width:
                frame = frame.resize((width, int(frame.height * width / frame.width)))
            frame.save(dest / f"f{i:03d}.png")
        (dest / "durations.json").write_text(json.dumps(durations))
    except Exception:
        return [], []
    return load_beat_frames(str(base))


def load_beat_frames(gif_path: str) -> tuple[list[str], list[int]]:
    """Pre-extracted GIF frames for widgets that can't play animations.

    Returns (frame_paths, durations_ms). Frames live in <gif>_frames/ next
    to the gif with a durations.json. Empty lists when unavailable."""
    base = Path(gif_path)
    d = base.parent / f"{base.stem}_frames"
    dur_file = d / "durations.json"
    if not dur_file.is_file():
        return [], []
    try:
        durations = json.loads(dur_file.read_text())
    except (json.JSONDecodeError, OSError):
        return [], []
    frames = sorted(d.glob("f*.png"))
    if not frames or len(frames) != len(durations):
        return [], []
    return ([str(f) for f in frames],
            [max(20, int(x) or 90) for x in durations])


def media_label(alarm: dict) -> str:
    v = alarm.get("video")
    if v:
        return f"🎬 {Path(v).name}"
    return f"🔊 {sound_label(alarm)}"


def detect_bpm(path: str | None, default: float = 120.0) -> float:
    """Estimate a song's tempo (onset-flux autocorrelation). Falls back to
    `default` when detection is impossible. Result in the 70–180 BPM band."""
    import tempfile
    if not path or not Path(path).is_file():
        return default
    try:
        import numpy as np
    except ImportError:
        return default
    wav = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav = tmp.name
        r = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", path,
             "-t", "60", "-ac", "1", "-ar", "22050", "-f", "wav", wav],
            capture_output=True, timeout=120)
        if r.returncode != 0:
            return default
        import wave
        with wave.open(wav, "rb") as w:
            raw = w.readframes(w.getnframes())
        x = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
        hop, win = 512, 1024
        nfr = 1 + (x.size - win) // hop
        if nfr < 32:
            return default
        prev = None
        flux = np.zeros(nfr, dtype=np.float32)
        window = np.hanning(win)
        for i in range(nfr):
            mag = np.abs(np.fft.rfft(x[i * hop:i * hop + win] * window))
            if prev is not None:
                d = mag - prev
                flux[i] = np.sum(d[d > 0])
            prev = mag
        flux -= np.mean(flux)
        flux[flux < 0] = 0
        if np.max(flux) <= 0:
            return default
        sr_flux = 22050 / hop
        ac = np.correlate(flux, flux, mode="full")[len(flux) - 1:]
        lo = int(sr_flux * 60 / 200)
        hi = min(int(sr_flux * 60 / 60), len(ac) - 1)
        if hi <= lo:
            return default
        ac[:lo] = 0
        peak = lo + int(np.argmax(ac[lo:hi]))
        if peak <= 0:
            return default
        bpm = 60 * sr_flux / peak
        while bpm < 70:
            bpm *= 2
        while bpm > 180:
            bpm /= 2
        return round(float(bpm), 1)
    except Exception:
        return default
    finally:
        try:
            if wav:
                Path(wav).unlink(missing_ok=True)
        except OSError:
            pass


def ring_audio_path(alarm: dict) -> str:
    """What the ringer loops: custom music, else video clip's audio, else default."""
    s = alarm.get("sound")
    if s and Path(s).is_file():
        return s
    v = alarm.get("video")
    if v and Path(v).is_file():
        return v
    return default_sound_path()


def import_video(src: str, seconds: int = VIDEO_CLIP_SECONDS) -> str | None:
    """Copy a video in and trim it to `seconds` (H.264 + AAC .mp4).

    Shorter sources keep their own length. Returns the clip path or None."""
    s = Path(src)
    if not s.is_file():
        return None
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    dest = VIDEOS_DIR / f"{s.stem}_{seconds}s.mp4"
    n = 1
    while dest.exists():
        dest = VIDEOS_DIR / f"{s.stem}_{seconds}s_{n}.mp4"
        n += 1
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", str(s), "-t", str(seconds),
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
             "-c:a", "aac", "-movflags", "+faststart", str(dest)],
            capture_output=True, timeout=600,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    return str(dest) if result.returncode == 0 and dest.exists() else None


def send_notification(title: str, body: str) -> None:
    try:
        subprocess.run(
            ["notify-send", "-u", "critical", "-a", "SayAlarm",
             "-i", "appointment-soon", title, body],
            check=False, capture_output=True, timeout=10,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        pass


def fire_alarm(alarm: dict, app_path: str, via_snooze: bool = False) -> None:
    """Notify + speech (3x) + popup + continuous ringing.
    The daemon sets alarm["ringing"]=True and spawns the ringer;
    ringing only stops on dismiss/snooze/delete or the failsafe cutoff.
    Caller must save store afterwards."""
    note = (alarm.get("note") or "").strip()
    title = "⏰ Alarm"
    body = note if note else "Time's up!"
    spoken = f"Alarm. {note}" if note else "Alarm. Time is up."
    if via_snooze:
        title = "⏰ Snoozed alarm"
        spoken = f"Again. {note}" if note else "Snoozed alarm."

    send_notification(title, body)
    alarm["ducked_players"] = duck_players()  # pause music; resume on dismiss
    voice = alarm.get("voice")
    if voice and Path(voice).is_file() and not via_snooze:
        play_voice_note(voice)  # your own recorded voice instead of TTS
    else:
        if alarm.get("briefing") and not via_snooze:
            spoken = f"{get_briefing(datetime.now())} {spoken}"
        speak(spoken, times=3)
    # Continuous ringer loop (stops on dismiss/snooze/cutoff).
    try:
        subprocess.Popen([sys.executable, app_path, "--ring", alarm["id"]],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (FileNotFoundError, OSError):
        play_sound(custom=alarm.get("sound"))  # fallback: short ring
    # Popup window so the note is unmissable in Ryoku/Hyprland.
    try:
        subprocess.Popen([sys.executable, app_path, "--popup", alarm["id"]],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (FileNotFoundError, OSError):
        pass
