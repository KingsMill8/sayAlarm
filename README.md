# SayAlarm ⏰🗣️

Set an alarm with a note. When it fires, Ryoku shows a critical
notification, plays your alarm sound, opens an unmissable anime popup, and
**speaks your note aloud 3 times, then stops** (offline voice via espeak-ng).

Works even when the app is closed: a systemd user service
(`sayalarm-daemon.service`) checks every 10 seconds.

## Install

```bash
# 1. deps (Arch): espeak-ng python-gobject gtk4 libadwaita mpv ffmpeg
#    Debian/Ubuntu: python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 libnotify-bin espeak-ng mpv ffmpeg
# 2. download + install:
git clone https://github.com/KingsMill8/sayAlarm.git
cd sayAlarm
bash install.sh       # launcher + always-on service
```

Or press Super+Space → **SayAlarm**.

## Layout

- `sayalarm.py`, `alarm_lib.py` — the app
- `assets/beat.gif` — dancing-GIF source (frames extract on first run)
- `ryoku-bar-widget/` — the Ryoku QS Bar plugin (`⏰ 07:30 · in 3h`
  live on the bar; install with
  `ryoku plugin add ryoku-bar-widget --bar --yes`)

## Custom music 🎵

In the Add/Edit dialog hit **🎵 Choose…**, pick any MP3/OGG/WAV/M4A
from your Music, Desktop or Downloads folder (or anywhere) — it's
copied into `~/.local/share/sayalarm/sounds/` and plays as that
alarm's sound. Hit **▶** to preview, **Reset** for the default beep.
Each alarm shows its sound (🔊 …) under its time.

## Video alarms 📺

Pick a **video file** in the same 🎵📹 Choose dialog — it's trimmed
to **30 seconds** automatically and stored in
`~/.local/share/sayalarm/videos/`. When the alarm fires:

- the **clip plays on loop in the popup** (muted display 📺)
- its **audio becomes the ringing sound**, looping until you dismiss
- your note is still spoken 3× over it

## Dancing GIF that grooves to your song 🎶

Every ringing popup features a dancing anime Eevee (`assets/beat.gif`,
frames in `assets/beat_frames/`) that **bounces on each beat** of your
alarm's song or video audio. The GIF is frame-cycled as PNGs (this
box can't play GIF animations directly) while a beat-synced pulse
scales it on every beat. Tempo is auto-detected (numpy onset
analysis, ~2% accuracy) on first ring and saved with the alarm, so
the groove is instant next time. No custom music? It vibes at a
default 120 BPM. Swap in any GIF by replacing `assets/beat.gif` and
deleting `assets/beat_frames/` — frames re-extract on next launch.

## Run

After installing, press Super+Space → **SayAlarm**
(or `python3 sayalarm.py` from your clone).

## Files

- `sayalarm.py` — GTK4/Libadwaita app, popup, `--daemon`/`--ring`/`--sunrise` loops, `--pomodoro`
- `alarm_lib.py` — alarm store + trigger/speech/duck/briefing/BPM logic
- alarms live in `~/.local/share/sayalarm/alarms.json`

## Power features

- 🔁 **Interval nags**: repeat "Every X min" between two times (e.g. water every 2h, 9:00–21:00)
- 🧮 **Dismiss challenge**: none, math problem, or type-your-note to unlock ✅ Done
- 🎙️ **Voice notes**: record 8s with your mic, played instead of the robot voice
- ⏸️ **Music auto-duck**: playing music pauses when the alarm fires, resumes on dismiss/snooze
- 🌅 **Sunrise wake-up**: set minutes → screen brightness ramps up before the alarm
- 🌦️ **Weather briefing**: alarm speaks greeting + time + current weather (cached, offline-safe)
- 🍅 **Pomodoro**: footer button opens focus/break timer with Eevee cheering
- 🧩 **Bar widget**: `~/Documents/ryoku-plugins/sayalarm` → `⏰ 07:30 · in 3h` live on the Ryoku bar
