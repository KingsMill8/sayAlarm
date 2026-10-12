#!/usr/bin/env python3
"""SayAlarm — set alarms with notes; Ryoku reminds you and speaks the note aloud.

Modes:
  sayalarm.py            launch the desktop app
  sayalarm.py --daemon   background loop (run by systemd user service)
  sayalarm.py --popup ID show the ringing popup for one alarm
"""
from __future__ import annotations

import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

APP_PATH = str(Path(__file__).resolve())
APP_NAME = "SayAlarm"
BEAT_GIF = str(Path(APP_PATH).parent / "assets" / "beat.gif")
DEFAULT_BEAT_BPM = 120.0

import alarm_lib as lib

try:
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    gi.require_version("Gdk", "4.0")
    from gi.repository import Adw, Gdk, Gio, GLib, Gtk
    GUI_OK = True
except (ImportError, ValueError):
    GUI_OK = False


# ------------------------------------------------- anime CSS -------------
# GTK4 supports @keyframes: swinging bell, rainbow text, screen shake,
# popping title, floating sparkles and a pulsing Add button.
ANIM_CSS = """
@keyframes bell-swing {
  0%   { transform: rotate(-25deg) scale(1); }
  50%  { transform: rotate(25deg) scale(1.25); }
  100% { transform: rotate(-25deg) scale(1); }
}
.bell {
  font-size: 76px;
  animation: bell-swing 0.7s ease-in-out infinite;
}
@keyframes wakeup-pop {
  0%   { transform: scale(0.4); opacity: 0; }
  60%  { transform: scale(1.2); opacity: 1; }
  100% { transform: scale(1); opacity: 1; }
}
.wakeup {
  font-size: 30px;
  font-weight: 900;
  letter-spacing: 2px;
  animation: wakeup-pop 0.6s ease-out both;
}
@keyframes rainbow-cycle {
  0%   { color: #ff5e5e; }
  20%  { color: #ffb84d; }
  40%  { color: #f5f066; }
  60%  { color: #5eff8a; }
  80%  { color: #5eb8ff; }
  100% { color: #c77dff; }
}
.rainbow { animation: rainbow-cycle 1.6s linear infinite; }
@keyframes screen-shake {
  0%   { transform: translate(-4px, 2px); }
  25%  { transform: translate(4px, -3px); }
  50%  { transform: translate(-3px, -2px); }
  75%  { transform: translate(3px, 3px); }
  100% { transform: translate(-4px, 2px); }
}
.ringing { animation: screen-shake 0.35s linear infinite; }
.ring-bg {
  background-image: linear-gradient(135deg, #2b1055 0%, #7597de 100%);
  border-radius: 18px;
}
@keyframes float-rise {
  0%   { transform: translateY(14px) scale(0.7); opacity: 0; }
  30%  { opacity: 1; }
  100% { transform: translateY(-46px) scale(1.2); opacity: 0; }
}
.sparkle {
  font-size: 26px;
  animation: float-rise 1.4s ease-in infinite;
}
@keyframes glow-pulse {
  0%   { opacity: 1; }
  50%  { opacity: 0.55; }
  100% { opacity: 1; }
}
.add-pulse { animation: glow-pulse 2s ease-in-out infinite; }
@keyframes row-slide {
  from { transform: translateX(-24px); opacity: 0; }
  to   { transform: translateX(0); opacity: 1; }
}
.alarm-row { animation: row-slide 0.35s ease-out both; }

/* ---------- advanced main-window theme ---------- */
.hero {
  background-image: linear-gradient(135deg, #2b1055 0%, #6a4c93 55%, #1982c4 100%);
  border-radius: 20px;
  padding: 20px;
}
.clock-big {
  font-size: 58px;
  font-weight: 800;
  color: white;
}
.hero-date { color: rgba(255,255,255,0.85); font-size: 14px; }
.next-alarm { color: #ffe66d; font-weight: 800; font-size: 17px; }
.next-none { color: rgba(255,255,255,0.75); font-size: 14px; }
.section-title { font-weight: 800; font-size: 15px; }
.alarm-card {
  background-color: rgba(255,255,255,0.055);
  border: 1px solid rgba(255,255,255,0.10);
  border-radius: 16px;
  padding: 12px 14px;
}
.time-big { font-size: 34px; font-weight: 800; }
.rep-dot { font-size: 20px; }
.chip { font-size: 12px; opacity: 0.8; }
.quick-bar {
  background-color: rgba(255,255,255,0.055);
  border: 1px solid rgba(255,255,255,0.10);
  border-radius: 14px;
  padding: 10px 12px;
}
.daemon-on { color: #5eff8a; font-weight: 700; }
.daemon-off { color: #ff5e5e; font-weight: 700; }
.empty-emoji { font-size: 52px; }
.dlg-title { font-size: 22px; font-weight: 800; }
@keyframes hero-breathe {
  0%   { opacity: 1; }
  50%  { opacity: 0.92; }
  100% { opacity: 1; }
}
.hero-live { animation: hero-breathe 3s ease-in-out infinite; }
@keyframes beat-bounce {
  0%   { transform: scale(1); }
  30%  { transform: scale(1.12) rotate(-1.5deg); }
  60%  { transform: scale(0.97) rotate(1.5deg); }
  100% { transform: scale(1); }
}
.beat { animation: beat-bounce 0.5s ease-in-out infinite; }
.alarm-list { background: transparent; }
.alarm-list row { background: transparent; padding: 3px 0; }
"""


def load_anime_css() -> None:
    display = Gdk.Display.get_default()
    if display is None:
        return
    provider = Gtk.CssProvider()
    provider.load_from_data(ANIM_CSS.encode())
    Gtk.StyleContext.add_provider_for_display(
        display,
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )


# ---------------------------------------------------------------- daemon ---

def daemon_loop() -> None:
    print("SayAlarm daemon started.", flush=True)
    while True:
        try:
            now = datetime.now()
            alarms = lib.load_alarms()
            changed = False
            for alarm in alarms:
                # Sunrise glow: start ramping brightness before the alarm.
                start = lib.sunrise_start_for(alarm, now)
                if start is not None and start <= now and \
                        alarm.get("sunrise_done") != now.strftime("%Y-%m-%d"):
                    alarm["sunrise_done"] = now.strftime("%Y-%m-%d")
                    try:
                        subprocess.Popen(
                            [sys.executable, APP_PATH, "--sunrise", alarm["id"]],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    except (FileNotFoundError, OSError):
                        pass
                    changed = True
                if lib.is_snooze_due(alarm, now):
                    lib.fire_alarm(alarm, APP_PATH, via_snooze=True)
                    alarm["snooze_until"] = 0
                    alarm["ringing"] = True  # loops until dismissed
                    alarm["last_fired_min"] = lib.minute_key(now)
                    changed = True
                elif lib.is_regular_due(alarm, now):
                    lib.fire_alarm(alarm, APP_PATH)
                    alarm["ringing"] = True  # loops until dismissed
                    alarm["last_fired_min"] = lib.minute_key(now)
                    if alarm.get("repeat", "once") == "once":
                        alarm["enabled"] = False  # one-shot: turn off after firing
                    changed = True
            if changed:
                lib.save_alarms(alarms)
        except Exception as exc:  # never let the daemon die
            print(f"daemon error: {exc}", flush=True)
        time.sleep(10)


RING_MAX_MINUTES = 10  # failsafe: never ring longer than this


def ringer_loop(alarm_id: str) -> None:
    """Loop the alarm's sound until dismissed/snoozed/deleted or cutoff.

    Started detached by the daemon on every firing. Polls the store so
    Dismiss / Snooze / window-close stops the sound within ~1 second."""
    import time as _t
    deadline = _t.time() + RING_MAX_MINUTES * 60
    print(f"Ringer started for {alarm_id}", flush=True)
    while _t.time() < deadline:
        alarm = next((a for a in lib.load_alarms() if a["id"] == alarm_id), None)
        if alarm is None or not alarm.get("ringing", False):
            break
        sound = lib.ring_audio_path(alarm)
        cmd = lib.player_cmd(sound) or lib.player_cmd(lib.default_sound_path())
        if cmd is None:
            break
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
        except OSError:
            break
        while proc.poll() is None:
            _t.sleep(1)
            alarm = next((a for a in lib.load_alarms()
                          if a["id"] == alarm_id), None)
            if alarm is None or not alarm.get("ringing", False) \
                    or _t.time() >= deadline:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.SubprocessError:
                    proc.kill()
                    try:
                        proc.wait(timeout=2)
                    except subprocess.SubprocessError:
                        pass
                break
    lib.stop_ringing(alarm_id)
    lib.unduck_alarm(alarm_id)  # resume music paused for this alarm
    print(f"Ringer stopped for {alarm_id}", flush=True)


def sunrise_loop(alarm_id: str) -> None:
    """Ramp screen brightness up like a sunrise until the alarm fires.

    Started detached by the daemon ~sunrise_min before firing. Stops when
    the alarm starts ringing, is disabled/deleted, or after 45 minutes."""
    import time as _t
    print(f"Sunrise started for {alarm_id}", flush=True)
    ceiling = lib.brightness_max()
    if ceiling is None:
        return
    deadline = _t.time() + 45 * 60
    start_ts = _t.time()
    # Total ramp time = the alarm's sunrise_min (min 1).
    total = 60.0
    alarm = next((a for a in lib.load_alarms() if a["id"] == alarm_id), None)
    if alarm is not None:
        total = max(60.0, float(alarm.get("sunrise_min", 10) or 10) * 60)
    floor = max(1, ceiling // 20)  # start near-dark
    lib.set_brightness(floor)
    while _t.time() < deadline:
        _t.sleep(15)
        alarm = next((a for a in lib.load_alarms() if a["id"] == alarm_id), None)
        if alarm is None or not alarm.get("enabled", True) \
                or alarm.get("ringing", False):
            break  # fired, disabled, or deleted
        progress = min(1.0, (_t.time() - start_ts) / total)
        lib.set_brightness(int(floor + (ceiling - floor) * progress))
        if progress >= 1.0:
            break
    print(f"Sunrise done for {alarm_id}", flush=True)


# ---------------------------------------------------------------- GUI -----

if GUI_OK:

    class AlarmDialog(Adw.Window):
        def __init__(self, parent: Gtk.Window, alarm: dict | None,
                     on_done):
            super().__init__(transient_for=parent, modal=True,
                             title="Edit alarm" if alarm else "New alarm",
                             default_width=380)
            self.alarm = alarm
            self.on_done = on_done

            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            box.set_margin_top(20); box.set_margin_bottom(20)
            box.set_margin_start(20); box.set_margin_end(20)
            self.set_content(box)

            title = Gtk.Label(
                label="✏️ Edit alarm" if alarm else "⏰ New alarm",
                css_classes=["dlg-title"], halign=Gtk.Align.CENTER)
            box.append(title)

            # Time pickers
            time_row = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER)
            now = datetime.now()
            h0 = alarm["hour"] if alarm else now.hour
            m0 = alarm["min"] if alarm else (now.minute + 1) % 60
            self.hour_spin = Gtk.SpinButton.new_with_range(0, 23, 1)
            self.hour_spin.set_value(h0)
            self.hour_spin.set_size_request(90, 48)
            self.min_spin = Gtk.SpinButton.new_with_range(0, 59, 1)
            self.min_spin.set_value(m0)
            self.min_spin.set_size_request(90, 48)
            for spin in (self.hour_spin, self.min_spin):
                spin.get_style_context().add_class("title-1")
            time_row.append(self.hour_spin)
            colon = Gtk.Label(label=":", css_classes=["title-1"])
            time_row.append(colon)
            time_row.append(self.min_spin)
            box.append(time_row)

            # Note
            self.note_entry = Gtk.Entry(placeholder_text="Note — e.g. Take the pizza out!")
            if alarm:
                self.note_entry.set_text(alarm.get("note", ""))
            box.append(self.note_entry)

            # Alarm sound — default beep, your own music, or a video clip
            self.sound_path: str | None = alarm.get("sound") if alarm else None
            self.video_path: str | None = alarm.get("video") if alarm else None
            snd_row = Gtk.Box(spacing=8)
            snd_row.append(Gtk.Label(label="Media"))
            self.sound_label = Gtk.Label(
                label=self._media_name(),
                xalign=0, hexpand=True, ellipsize=3)
            snd_row.append(self.sound_label)
            choose_btn = Gtk.Button(label="🎵📹 Choose…")
            choose_btn.set_tooltip_text("Pick music OR a small video (trimmed to 30s)")
            choose_btn.connect("clicked", self._on_choose_sound)
            preview_btn = Gtk.Button(label="▶")
            preview_btn.set_tooltip_text("Preview sound")
            preview_btn.connect("clicked",
                                lambda *_: lib.preview(
                                    self.sound_path or self.video_path))
            reset_btn = Gtk.Button(label="Reset")
            reset_btn.set_tooltip_text("Back to default alarm sound")
            reset_btn.connect("clicked", self._on_reset_sound)
            snd_row.append(choose_btn)
            snd_row.append(preview_btn)
            snd_row.append(reset_btn)
            box.append(snd_row)

            # Voice note — record with the mic, played instead of robot voice
            self.voice_path: str | None = alarm.get("voice") if alarm else None
            vrow = Gtk.Box(spacing=8)
            vrow.append(Gtk.Label(label="Voice"))
            self.voice_label = Gtk.Label(
                label=Path(self.voice_path).name if self.voice_path else "Robot voice",
                xalign=0, hexpand=True, ellipsize=3)
            vrow.append(self.voice_label)
            rec_btn = Gtk.Button(label="🎙️ Record 8s")
            rec_btn.connect("clicked", self._on_record)
            vplay_btn = Gtk.Button(label="▶")
            vplay_btn.set_tooltip_text("Play voice note")
            vplay_btn.connect("clicked",
                              lambda *_: lib.preview(self.voice_path)
                              if self.voice_path else None)
            vclear_btn = Gtk.Button(label="Reset")
            vclear_btn.connect("clicked", self._on_voice_reset)
            vrow.append(rec_btn); vrow.append(vplay_btn); vrow.append(vclear_btn)
            box.append(vrow)

            # Repeat
            rep_row = Gtk.Box(spacing=8)
            rep_row.append(Gtk.Label(label="Repeat"))
            self.repeat_drop = Gtk.DropDown.new_from_strings(
                [lib.REPEAT_LABELS[r] for r in lib.REPEATS])
            start_rep = alarm.get("repeat", "once") if alarm else "once"
            if start_rep not in lib.REPEATS:
                start_rep = "once"
            self.repeat_drop.set_selected(lib.REPEATS.index(start_rep))
            self.repeat_drop.connect("notify::selected", lambda *_: self._toggle_days())
            rep_row.append(self.repeat_drop)
            box.append(rep_row)

            # Weekday toggles for custom
            self.day_checks: list[Gtk.CheckButton] = []
            day_row = Gtk.Box(spacing=4, halign=Gtk.Align.CENTER)
            days_on = set(alarm.get("days", [])) if alarm else {datetime.now().weekday()}
            for i, name in enumerate(lib.DAY_NAMES):
                cb = Gtk.CheckButton(label=name)
                cb.set_active(i in days_on)
                day_row.append(cb)
                self.day_checks.append(cb)
            self.day_box = day_row
            box.append(day_row)

            # Interval nags: every X min between two times
            self.int_box = Gtk.Box(spacing=6, halign=Gtk.Align.CENTER)
            self.int_box.append(Gtk.Label(label="Every"))
            self.every_spin = Gtk.SpinButton.new_with_range(1, 720, 1)
            self.every_spin.set_value(alarm.get("every_min", 30) if alarm else 30)
            self.int_box.append(self.every_spin)
            self.int_box.append(Gtk.Label(label="min,"))
            self.from_h = Gtk.SpinButton.new_with_range(0, 23, 1)
            self.from_h.set_value(alarm.get("from_h", 9) if alarm else 9)
            self.from_m = Gtk.SpinButton.new_with_range(0, 59, 1)
            self.from_m.set_value(alarm.get("from_m", 0) if alarm else 0)
            self.to_h = Gtk.SpinButton.new_with_range(0, 23, 1)
            self.to_h.set_value(alarm.get("to_h", 21) if alarm else 21)
            self.to_m = Gtk.SpinButton.new_with_range(0, 59, 1)
            self.to_m.set_value(alarm.get("to_m", 0) if alarm else 0)
            for w, tip in ((self.from_h, "From hour"), (self.from_m, "From minute"),
                           (self.to_h, "To hour"), (self.to_m, "To minute")):
                w.set_tooltip_text(tip)
                self.int_box.append(w)
            box.append(self.int_box)

            # Challenge + sunrise + briefing
            opt_row = Gtk.Box(spacing=8)
            opt_row.append(Gtk.Label(label="Unlock"))
            self.chal_drop = Gtk.DropDown.new_from_strings(
                [lib.CHALLENGE_LABELS[c] for c in lib.CHALLENGES])
            start_ch = alarm.get("challenge", "none") if alarm else "none"
            if start_ch not in lib.CHALLENGES:
                start_ch = "none"
            self.chal_drop.set_selected(lib.CHALLENGES.index(start_ch))
            self.chal_drop.set_tooltip_text("Prove you're awake to dismiss")
            opt_row.append(self.chal_drop)
            opt_row.append(Gtk.Label(label="🌅"))
            self.sun_spin = Gtk.SpinButton.new_with_range(0, 30, 5)
            self.sun_spin.set_value(alarm.get("sunrise_min", 0) if alarm else 0)
            self.sun_spin.set_tooltip_text("Sunrise glow minutes before (0 = off)")
            opt_row.append(self.sun_spin)
            box.append(opt_row)

            self.brief_check = Gtk.CheckButton(label="🌦️ Speak weather + greeting")
            self.brief_check.set_active(bool(alarm.get("briefing")) if alarm else False)
            box.append(self.brief_check)
            self._toggle_days()

            # Buttons
            btn_row = Gtk.Box(spacing=8, halign=Gtk.Align.END)
            test_btn = Gtk.Button(label="🔊 Hear it")
            test_btn.connect("clicked", self._on_test)
            save_btn = Gtk.Button(label="Save", css_classes=["suggested-action"])
            save_btn.connect("clicked", self._on_save)
            cancel_btn = Gtk.Button(label="Cancel")
            cancel_btn.connect("clicked", self._on_cancel)
            btn_row.append(test_btn); btn_row.append(cancel_btn); btn_row.append(save_btn)
            box.append(btn_row)

        def _toggle_days(self):
            rep = lib.REPEATS[self.repeat_drop.get_selected()]
            self.day_box.set_visible(rep == "custom")
            self.int_box.set_visible(rep == "interval")

        def _on_record(self, btn):
            btn.set_sensitive(False)
            self.voice_label.set_text("🔴 Recording… speak now (8s)")
            threading.Thread(target=self._record_bg, args=(btn,),
                             daemon=True).start()

        def _record_bg(self, btn):
            import time as _t, uuid as _u
            dest = str(lib.SOUNDS_DIR / f"voice_{_t.strftime('%Y%m%d_%H%M%S')}.wav")
            lib.SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
            rec = None
            for cmd in (["timeout", "9", "parecord", "--channels=1",
                         "--rate=16000", dest],
                        ["arecord", "-d", "8", "-f", "cd", dest]):
                try:
                    rec = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                           stderr=subprocess.DEVNULL)
                    break
                except (FileNotFoundError, OSError):
                    continue
            if rec is None:
                GLib.idle_add(self._record_done, btn, None)
                return
            try:
                rec.wait(timeout=12)
            except subprocess.SubprocessError:
                try:
                    rec.kill()
                except OSError:
                    pass
            GLib.idle_add(self._record_done, btn,
                          dest if Path(dest).is_file() else None)

        def _record_done(self, btn, dest):
            btn.set_sensitive(True)
            if dest:
                old = self.voice_path
                self.voice_path = dest
                self.voice_label.set_text(Path(dest).name)
                lib.preview(dest)
                if old and old != dest:
                    try:
                        Path(old).unlink(missing_ok=True)
                    except OSError:
                        pass
            else:
                self.voice_label.set_text("⚠️ No mic / recorder found")
            return False

        def _on_voice_reset(self, _btn):
            if self.voice_path:
                try:
                    Path(self.voice_path).unlink(missing_ok=True)
                except OSError:
                    pass
            self.voice_path = None
            self.voice_label.set_text("Robot voice")

        def _on_test(self, _btn):
            text = self.note_entry.get_text().strip() or "This is how your alarm will sound."
            lib.speak(text, times=1)

        def _media_name(self) -> str:
            if self.video_path:
                return f"🎬 {Path(self.video_path).name}"
            if self.sound_path:
                return Path(self.sound_path).name
            return "Default alarm"

        def _on_choose_sound(self, _btn):
            dlg = Gtk.FileDialog(title="Pick alarm music or video 🎵📹")
            audio = Gtk.FileFilter(name="Audio files")
            for pat in ("*.mp3", "*.ogg", "*.oga", "*.wav",
                        "*.m4a", "*.flac", "*.opus"):
                audio.add_pattern(pat)
                audio.add_pattern(pat.upper())
            video = Gtk.FileFilter(name="Video files")
            for pat in ("*.mp4", "*.mkv", "*.webm", "*.mov",
                        "*.avi", "*.m4v"):
                video.add_pattern(pat)
                video.add_pattern(pat.upper())
            store = Gio.ListStore.new(Gtk.FileFilter)
            store.append(audio)
            store.append(video)
            dlg.set_filters(store)
            dlg.set_default_filter(audio)
            home = Gio.File.new_for_path(str(Path.home()))
            for cand in ("Videos", "Music", "Desktop", "Downloads"):
                d = home.get_child(cand)
                if d.query_exists(None):
                    dlg.set_initial_folder(d)
                    break
            dlg.open(self, None, self._sound_chosen)

        def _sound_chosen(self, dlg: Gtk.FileDialog, res):
            try:
                f = dlg.open_finish(res)
            except GLib.Error:
                return  # user cancelled
            if f is None or f.get_path() is None:
                return
            path = f.get_path()
            if Path(path).suffix.lower() in lib.VIDEO_EXTS:
                self.sound_label.set_text("⏳ Trimming video to 30s…")
                threading.Thread(target=self._import_video_bg, args=(path,),
                                 daemon=True).start()
                return
            dest = lib.import_sound(path)
            if dest:
                self.sound_path = dest
                self.video_path = None
                self.sound_label.set_text(self._media_name())
                lib.preview(dest)

        def _import_video_bg(self, path: str):
            dest = lib.import_video(path)
            GLib.idle_add(self._video_ready, dest)

        def _video_ready(self, dest: str | None):
            if dest:
                self.video_path = dest
                self.sound_path = None
                self.sound_label.set_text(self._media_name())
                lib.preview(dest)  # hear its audio
            else:
                self.sound_label.set_text("⚠️ Video failed — pick another file")
            return False

        def _on_reset_sound(self, _btn):
            self.sound_path = None
            self.video_path = None
            self.sound_label.set_text("Default alarm")

        def _on_save(self, _btn):
            rep = lib.REPEATS[self.repeat_drop.get_selected()]
            days = [i for i, cb in enumerate(self.day_checks) if cb.get_active()]
            if rep == "custom" and not days:
                days = [datetime.now().weekday()]
            base = dict(self.alarm) if self.alarm else {
                "id": uuid.uuid4().hex[:8],
                "one_shot_date": datetime.now().strftime("%Y-%m-%d"),
            }
            base.update({
                "hour": int(self.hour_spin.get_value()),
                "min": int(self.min_spin.get_value()),
                "note": self.note_entry.get_text().strip(),
                "repeat": rep,
                "days": days,
                "sound": self.sound_path,
                "video": self.video_path,
                "voice": self.voice_path,
                "challenge": lib.CHALLENGES[self.chal_drop.get_selected()],
                "sunrise_min": int(self.sun_spin.get_value()),
                "briefing": self.brief_check.get_active(),
                "every_min": int(self.every_spin.get_value()),
                "from_h": int(self.from_h.get_value()),
                "from_m": int(self.from_m.get_value()),
                "to_h": int(self.to_h.get_value()),
                "to_m": int(self.to_m.get_value()),
                "enabled": True if self.alarm is None else self.alarm.get("enabled", True),
                "snooze_until": 0,
            })
            if rep == "once":
                base["one_shot_date"] = datetime.now().strftime("%Y-%m-%d")
            self.on_done(base)
            self.destroy()

        def _on_cancel(self, _btn):
            self.on_done(None)
            self.destroy()


    class MainWindow(Adw.ApplicationWindow):
        def __init__(self, app: Adw.Application):
            super().__init__(application=app, title=APP_NAME, default_width=520,
                             default_height=560)
            self.alarms = lib.load_alarms()

            header = Adw.HeaderBar()
            title_lbl = Gtk.Label(label="⏰ SayAlarm", css_classes=["title-4"])
            header.set_title_widget(title_lbl)
            add_btn = Gtk.Button(label="✨ + Add alarm",
                                   css_classes=["suggested-action", "add-pulse"])
            add_btn.connect("clicked", self._on_add)
            header.pack_start(add_btn)

            toolbar = Adw.ToolbarView()
            self.set_content(toolbar)
            toolbar.add_top_bar(header)

            outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            toolbar.set_content(outer)

            # ---- hero: live clock + next-alarm countdown ----
            hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2,
                           halign=Gtk.Align.FILL, css_classes=["hero", "hero-live"])
            hero.set_margin_top(12); hero.set_margin_start(12); hero.set_margin_end(12)
            self.clock_label = Gtk.Label(label="--:--", css_classes=["clock-big"])
            hero.append(self.clock_label)
            self.date_label = Gtk.Label(label="", css_classes=["hero-date"])
            hero.append(self.date_label)
            self.next_label = Gtk.Label(label="", css_classes=["next-alarm"],
                                        wrap=True, justify=Gtk.Justification.CENTER)
            hero.append(self.next_label)
            outer.append(hero)

            self.status_label = Gtk.Label(margin_top=6, css_classes=["dim-label"])
            outer.append(self.status_label)

            # Quick reminder: note + "in X minutes", no clock math needed.
            quick = Gtk.Box(spacing=8, margin_top=4, margin_start=12, margin_end=12,
                            halign=Gtk.Align.CENTER, css_classes=["quick-bar"])
            self.quick_entry = Gtk.Entry(placeholder_text="⚡ Quick note… e.g. Check the oven",
                                         hexpand=True)
            self.quick_entry.set_size_request(200, -1)
            self.quick_entry.connect("activate", lambda *_: self._on_quick())
            self.quick_spin = Gtk.SpinButton.new_with_range(1, 720, 1)
            self.quick_spin.set_value(10)
            quick.append(self.quick_entry)
            quick.append(Gtk.Label(label="in"))
            quick.append(self.quick_spin)
            quick.append(Gtk.Label(label="min"))
            quick_btn = Gtk.Button(label="⏱ Remind me", css_classes=["suggested-action"])
            quick_btn.connect("clicked", lambda *_: self._on_quick())
            quick.append(quick_btn)
            outer.append(quick)

            outer.append(Gtk.Label(label="🔔 Your alarms", xalign=0,
                                   margin_top=8, margin_start=16,
                                   css_classes=["section-title"]))

            scroll = Gtk.ScrolledWindow(vexpand=True)
            self.listbox = Gtk.ListBox(css_classes=["alarm-list"], margin_top=4,
                                       margin_bottom=12, margin_start=12, margin_end=12,
                                       selection_mode=Gtk.SelectionMode.NONE)
            scroll.set_child(self.listbox)
            outer.append(scroll)

            footer = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER, margin_bottom=12)
            test_notif = Gtk.Button(label="Test notification")
            test_notif.connect("clicked", self._on_test_notif)
            footer.append(test_notif)
            daemon_btn = Gtk.Button(label="Restart reminder service")
            daemon_btn.connect("clicked", self._on_restart_daemon)
            footer.append(daemon_btn)
            pomo_btn = Gtk.Button(label="🍅 Pomodoro")
            pomo_btn.connect("clicked", self._on_pomodoro)
            footer.append(pomo_btn)
            outer.append(footer)

            self._refresh()
            self._tick_clock()
            GLib.timeout_add_seconds(15, self._tick)
            GLib.timeout_add_seconds(1, self._tick_clock)

        def _tick(self):
            self.alarms = lib.load_alarms()
            self._refresh()
            return True

        def _tick_clock(self):
            now = datetime.now()
            self.clock_label.set_text(now.strftime("%H:%M"))
            self.date_label.set_text(now.strftime("%A · %d %B %Y"))
            # Next upcoming alarm across the whole list.
            best = None  # (minutes, note)
            for alarm in self.alarms:
                ahead = lib.next_fire_in_minutes(alarm, now)
                if ahead is None:
                    continue
                if best is None or ahead < best[0]:
                    best = (ahead, (alarm.get("note") or "Alarm").strip())
            if best is None:
                self.next_label.set_text("💤 No alarms on — set one above!")
                self.next_label.add_css_class("next-none")
            else:
                self.next_label.set_text(
                    f"⏳ Next: “{best[1]}” {lib.fmt_countdown(best[0])}")
                self.next_label.remove_css_class("next-none")
            return True

        def _daemon_active(self) -> bool:
            try:
                r = subprocess.run(["systemctl", "--user", "is-active", "sayalarm-daemon.service"],
                                   capture_output=True, text=True, timeout=5)
                return r.stdout.strip() == "active"
            except (FileNotFoundError, subprocess.SubprocessError):
                return False

        def _refresh(self):
            while (row := self.listbox.get_row_at_index(0)) is not None:
                self.listbox.remove(row)
            now = datetime.now()
            if self._daemon_active():
                self.status_label.set_markup(
                    '<span foreground="#5eff8a" weight="bold">'
                    '● reminder service running</span>'
                    f'  ·  {len(self.alarms)} alarm(s)')
            else:
                self.status_label.set_markup(
                    '<span foreground="#ff5e5e" weight="bold">'
                    '○ reminder service OFF'
                    ' — hit “Restart reminder service” below</span>')
            if not self.alarms:
                empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6,
                                halign=Gtk.Align.CENTER, margin_top=36)
                empty.append(Gtk.Label(label="😴", css_classes=["empty-emoji"]))
                empty.append(Gtk.Label(label="No alarms yet — sweet dreams are\n"
                                              "made of hitting + Add alarm ✨",
                                       justify=Gtk.Justification.CENTER,
                                       css_classes=["dim-label"]))
                self.listbox.append(empty)
                return
            for alarm in sorted(self.alarms, key=lambda a: (a["hour"], a["min"])):
                self.listbox.append(self._row(alarm, now))

        def _row(self, alarm: dict, now: datetime) -> Gtk.Widget:
            rep = alarm.get("repeat", "once")
            color = lib.REPEAT_COLORS.get(rep, "#c77dff")
            card = Gtk.Box(spacing=12, css_classes=["alarm-card", "alarm-row"])
            card.set_margin_top(2); card.set_margin_bottom(2)

            dot = Gtk.Label(css_classes=["rep-dot"], valign=Gtk.Align.START)
            dot.set_markup(f'<span foreground="{color}">●</span>')
            dot.set_tooltip_text(lib.REPEAT_LABELS.get(rep, rep))
            card.append(dot)

            info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2,
                           hexpand=True)
            info.append(Gtk.Label(label=f"{alarm['hour']:02d}:{alarm['min']:02d}",
                                  xalign=0, css_classes=["time-big"]))
            note = (alarm.get("note") or "(no note)").strip()
            note_lbl = Gtk.Label(label=note, xalign=0, wrap=True,
                                 css_classes=["title-4"])
            info.append(note_lbl)
            when = lib.next_fire_text(alarm, now)
            rep_lbl = lib.repeat_label(alarm)
            extras = ""
            if alarm.get("challenge", "none") != "none":
                extras += "  🧮"
            if alarm.get("voice"):
                extras += "  🎙️"
            if int(alarm.get("sunrise_min", 0) or 0) > 0:
                extras += "  🌅"
            if alarm.get("briefing"):
                extras += "  🌦️"
            chips = Gtk.Label(
                label=f"{rep_lbl}  ·  {when}  ·  {lib.media_label(alarm)}{extras}",
                xalign=0, css_classes=["chip"])
            info.append(chips)
            card.append(info)

            side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                           valign=Gtk.Align.CENTER)
            toggle = Gtk.Switch(halign=Gtk.Align.END,
                                active=alarm.get("enabled", True))
            toggle.set_tooltip_text("On / off")
            toggle.connect("state-set", self._on_toggle, alarm["id"])
            side.append(toggle)
            btns = Gtk.Box(spacing=6, halign=Gtk.Align.END)
            edit = Gtk.Button(label="✏️ Edit")
            edit.connect("clicked", self._on_edit, alarm["id"])
            delete = Gtk.Button(label="🗑", css_classes=["destructive-action"])
            delete.set_tooltip_text("Delete alarm")
            delete.connect("clicked", self._on_delete, alarm["id"])
            btns.append(edit)
            btns.append(delete)
            side.append(btns)
            card.append(side)
            if not alarm.get("enabled", True):
                card.set_opacity(0.5)
            return card

        def _find(self, alarm_id: str) -> dict | None:
            return next((a for a in self.alarms if a["id"] == alarm_id), None)

        def _persist(self):
            lib.save_alarms(self.alarms)
            self._refresh()

        def _on_add(self, _btn):
            AlarmDialog(self, None, self._dialog_done).present()

        def _on_edit(self, _btn, alarm_id: str):
            alarm = self._find(alarm_id)
            if alarm:
                AlarmDialog(self, alarm, self._dialog_done).present()

        def _dialog_done(self, data: dict | None):
            if not data:
                return
            if any(a["id"] == data["id"] for a in self.alarms):
                self.alarms = [data if a["id"] == data["id"] else a
                               for a in self.alarms]
            else:
                self.alarms.append(data)
            self._persist()

        def _on_quick(self):
            from datetime import timedelta
            note = self.quick_entry.get_text().strip() or "Quick reminder!"
            target = datetime.now() + timedelta(
                minutes=int(self.quick_spin.get_value()))
            self.alarms.append({
                "id": uuid.uuid4().hex[:8],
                "hour": target.hour,
                "min": target.minute,
                "note": note,
                "repeat": "once",
                "days": [],
                "sound": None,
                "video": None,
                "voice": None,
                "challenge": "none",
                "sunrise_min": 0,
                "briefing": False,
                "every_min": 30,
                "from_h": 9, "from_m": 0, "to_h": 21, "to_m": 0,
                "enabled": True,
                "snooze_until": 0,
                "one_shot_date": target.strftime("%Y-%m-%d"),
            })
            self.quick_entry.set_text("")
            self._persist()
            lib.send_notification(
                "⏱ Reminder set",
                f"{target.strftime('%H:%M')} — {note}")

        def _on_toggle(self, _sw, state: bool, alarm_id: str):
            alarm = self._find(alarm_id)
            if alarm:
                alarm["enabled"] = state
                if state:
                    alarm["snooze_until"] = 0
                self._persist()
            return False

        def _on_delete(self, _btn, alarm_id: str):
            self.alarms = [a for a in self.alarms if a["id"] != alarm_id]
            self._persist()

        def _on_test_notif(self, _btn):
            lib.send_notification("⏰ SayAlarm test", "Reminders reach Ryoku just fine!")
            lib.speak("Say alarm test. Your reminders will speak like this.")

        def _on_restart_daemon(self, _btn):
            subprocess.run(["systemctl", "--user", "enable", "--now",
                            "sayalarm-daemon.service"],
                           capture_output=True, timeout=30)
            self._refresh()

        def _on_pomodoro(self, _btn):
            try:
                subprocess.Popen([sys.executable, APP_PATH, "--pomodoro"],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
            except (FileNotFoundError, OSError):
                pass


    class PopupWindow(Adw.ApplicationWindow):
        """Anime-style ringing window spawned by the daemon."""

        SPARKLES = ["✨", "💫", "⚡", "🌸", "💥", "⭐"]

        def __init__(self, app: Adw.Application, alarm: dict):
            super().__init__(application=app, title="⏰ Alarm!",
                             default_width=500, default_height=720)
            self.alarm = alarm
            # GTK4 has no urgency hint; the critical notify + sound carry that job.
            self._sparkle_idx = 0

            overlay = Gtk.Overlay()
            self.set_content(overlay)

            # Shaking anime background.
            bg = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                         halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER,
                         css_classes=["ring-bg", "ringing"])
            bg.set_margin_top(24); bg.set_margin_bottom(24)
            bg.set_margin_start(24); bg.set_margin_end(24)
            overlay.set_child(bg)

            bg.append(Gtk.Label(label="🔔", css_classes=["bell"]))
            wakeup_lbl = Gtk.Label(label="起きて! WAKE UP!",
                                   css_classes=["wakeup", "rainbow"])
            bg.append(wakeup_lbl)
            # Dancing anime GIF, bouncing on every beat of the song. 🎶
            # (Frame-cycled PNGs: this box can't play GIF animations itself.)
            self._gif_bg = bg
            self._gif_anchor = wakeup_lbl
            self._gif_pic: Gtk.Picture | None = None
            self._gif_frames, self._gif_durs = lib.load_beat_frames(BEAT_GIF)
            if self._gif_frames:
                self._setup_gif()
            elif Path(BEAT_GIF).is_file():
                # Fresh/changed gif: extract frames in the background.
                threading.Thread(target=self._extract_gif_bg, daemon=True).start()
            self._beat_provider: Gtk.CssProvider | None = None
            if self._gif_frames or Path(BEAT_GIF).is_file():
                self._beat_provider = Gtk.CssProvider()
                display = Gdk.Display.get_default()
                if display is not None:
                    Gtk.StyleContext.add_provider_for_display(
                        display, self._beat_provider,
                        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
                bpm = self.alarm.get("bpm") or 0
                if bpm:
                    self._apply_beat(float(bpm))
                else:
                    self._apply_beat(DEFAULT_BEAT_BPM)
                    threading.Thread(target=self._detect_beat_bg,
                                     daemon=True).start()
            t = Gtk.Label(label=f"⏰ {alarm['hour']:02d}:{alarm['min']:02d}",
                          css_classes=["title-1"])
            bg.append(t)
            # Video clip display (audio comes from the ringer loop, so the
            # clip plays muted here — pure anime display purpose 📺).
            self._video: Gtk.Video | None = None
            vid = alarm.get("video")
            if vid and Path(vid).is_file():
                self._video = Gtk.Video(
                    halign=Gtk.Align.CENTER, hexpand=True)
                self._video.set_file(Gio.File.new_for_path(vid))
                self._video.set_autoplay(True)
                self._video.set_size_request(400, 225)
                bg.append(self._video)
                GLib.timeout_add_seconds(3, self._video_tick)
            note = (alarm.get("note") or "Time's up!").strip()
            note_lbl = Gtk.Label(label=f"👉 {note}", wrap=True,
                                 justify=Gtk.Justification.CENTER,
                                 css_classes=["title-2"])
            bg.append(note_lbl)
            bg.append(Gtk.Label(label="⚡ NOTE POWER: MAX ⚡",
                                css_classes=["dim-label"]))
            bg.append(Gtk.Label(label="🔊 ringing until you hit ✅ Done!",
                                css_classes=["dim-label"]))

            btns = Gtk.Box(spacing=10, halign=Gtk.Align.CENTER, margin_top=6)
            voice = alarm.get("voice")
            if voice and Path(voice).is_file():
                again = Gtk.Button(label="🔊 Play again")
                again.connect("clicked",
                              lambda *_: lib.play_voice_note(voice, times=1))
            else:
                again = Gtk.Button(label="🔊 Say again")
                again.connect("clicked",
                              lambda *_: lib.speak(note, times=1, background=True))
            snooze5 = Gtk.Button(label="😴 5 min")
            snooze5.connect("clicked", self._snooze, 5)
            snooze10 = Gtk.Button(label="😴 10 min")
            snooze10.connect("clicked", self._snooze, 10)
            self.dismiss_btn = Gtk.Button(label="✅ Done!",
                                          css_classes=["suggested-action"])
            self.dismiss_btn.connect("clicked", self._on_dismiss)
            for b in (again, snooze5, snooze10, self.dismiss_btn):
                btns.append(b)
            bg.append(btns)

            # Wake-up challenge: lock Done until solved. 🧮
            self._challenge_ok = True
            chal = alarm.get("challenge", "none")
            if chal == "math":
                import random as _r
                op = _r.choice(["+", "-", "×"])
                if op == "+":
                    a, b = _r.randint(3, 29), _r.randint(3, 29)
                    ans = a + b
                elif op == "-":
                    b, ans = _r.randint(1, 9), _r.randint(5, 30)
                    a = ans + b  # keep it positive: (ans+b) − b = ans
                else:
                    a, b = _r.randint(2, 9), _r.randint(2, 9)
                    ans = a * b
                self._challenge_ans = str(ans)
                if op == "-":
                    q = f"{a} − {b} = ?"
                elif op == "×":
                    q = f"{a} × {b} = ?"
                else:
                    q = f"{a} + {b} = ?"
                self._challenge_gate(bg, btns,
                                    f"🧮 Prove you're awake:  {q}")
            elif chal == "type" and note and note != "Time's up!":
                self._challenge_ans = note.strip().lower()
                self._challenge_gate(
                    bg, btns, "⌨️ Type your note to dismiss:")
            # Closing the window any other way also stops the ringing.
            self.connect("close-request", self._on_dismiss)

            # Floating sparkle layer cycling emoji across the top.
            self.sparkle = Gtk.Label(label="✨", css_classes=["sparkle"],
                                     halign=Gtk.Align.START, valign=Gtk.Align.START,
                                     margin_top=30, margin_start=60)
            overlay.add_overlay(self.sparkle)
            GLib.timeout_add(700, self._cycle_sparkle)
            # Alternate the bell emoji for extra hype.
            self._bell_lbl = None
            for child in self._box_children(bg):
                if isinstance(child, Gtk.Label) and "bell" in child.get_css_classes():
                    self._bell_lbl = child
            GLib.timeout_add(500, self._flip_bell)
            # No auto-speech here: the daemon already speaks the note 3×.
            # "Say again" replays it on demand.

        @staticmethod
        def _box_children(box: Gtk.Box):
            child = box.get_first_child()
            while child is not None:
                yield child
                child = child.get_next_sibling()

        def _cycle_sparkle(self):
            self._sparkle_idx = (self._sparkle_idx + 1) % len(self.SPARKLES)
            self.sparkle.set_text(self.SPARKLES[self._sparkle_idx])
            # Retrigger the float animation.
            self.sparkle.remove_css_class("sparkle")
            self.sparkle.add_css_class("sparkle")
            return True

        def _setup_gif(self):
            """Insert the dancing-GIF box right under the title."""
            beat_box = Gtk.Box(halign=Gtk.Align.CENTER, css_classes=["beat"])
            self._gif_pic = Gtk.Picture(halign=Gtk.Align.CENTER)
            self._gif_pic.set_filename(self._gif_frames[0])
            self._gif_pic.set_size_request(300, 170)
            beat_box.append(self._gif_pic)
            self._gif_bg.insert_child_after(beat_box, self._gif_anchor)
            self._gif_idx = 0
            GLib.timeout_add(self._gif_durs[0], self._advance_gif)

        def _extract_gif_bg(self):
            frames, durs = lib.extract_beat_frames(BEAT_GIF)
            if frames:
                self._gif_frames, self._gif_durs = frames, durs
                GLib.idle_add(self._gif_ready)

        def _gif_ready(self):
            if self._gif_pic is None and self._gif_frames:
                self._setup_gif()
            return False

        def _advance_gif(self):
            """Next dance frame (each on screen for its own duration)."""
            if not self._gif_frames:
                return False
            self._gif_idx = (self._gif_idx + 1) % len(self._gif_frames)
            self._gif_pic.set_filename(self._gif_frames[self._gif_idx])
            GLib.timeout_add(self._gif_durs[self._gif_idx], self._advance_gif)
            return False

        def _apply_beat(self, bpm: float):
            """Set the GIF bounce interval to one beat of the song."""
            if self._beat_provider is None:
                return False
            interval = 60.0 / max(40.0, float(bpm))
            self._beat_provider.load_from_data(
                f".beat {{ animation: beat-bounce {interval:.3f}s "
                f"ease-in-out infinite; }}".encode())
            return False

        def _detect_beat_bg(self):
            media = self.alarm.get("sound") or self.alarm.get("video")
            bpm = lib.detect_bpm(media) if media else DEFAULT_BEAT_BPM
            alarms = lib.load_alarms()  # persist so next firing is instant
            for a in alarms:
                if a["id"] == self.alarm["id"]:
                    a["bpm"] = bpm
                    self.alarm["bpm"] = bpm
            lib.save_alarms(alarms)
            GLib.idle_add(self._apply_beat, bpm)

        def _video_tick(self):
            """Keep the clip looping (muted — the ringer plays its audio)."""
            if self._video is None:
                return False
            try:
                ms = self._video.get_media_stream()
                if ms is None:
                    return True
                ms.set_volume(0.0)
                if not ms.get_playing():
                    try:
                        ms.seek(0)
                    except GLib.Error:
                        pass
                    ms.play()
            except GLib.Error:
                pass
            return True

        def _flip_bell(self):
            if self._bell_lbl is not None:
                cur = self._bell_lbl.get_text()
                self._bell_lbl.set_text("⏰" if cur == "🔔" else "🔔")
            return True

        def _challenge_gate(self, bg: Gtk.Box, btns: Gtk.Box, prompt: str):
            """Lock ✅ Done behind a question; sits above the buttons."""
            self._challenge_ok = False
            self.dismiss_btn.set_sensitive(False)
            gate = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER, margin_top=4)
            gate.append(Gtk.Label(label=prompt, css_classes=["title-4"]))
            self._chal_entry = Gtk.Entry(placeholder_text="answer…")
            self._chal_entry.set_size_request(150, -1)
            self._chal_entry.connect("activate", lambda *_: self._check_challenge())
            go = Gtk.Button(label="Unlock 🔓")
            go.connect("clicked", lambda *_: self._check_challenge())
            gate.append(self._chal_entry)
            gate.append(go)
            self._chal_msg = Gtk.Label(label="", halign=Gtk.Align.CENTER)
            bg.remove(btns)  # re-insert below so the gate sits above buttons
            bg.append(gate)
            bg.append(self._chal_msg)
            bg.append(btns)

        def _check_challenge(self):
            got = self._chal_entry.get_text().strip().lower()
            if got and got == self._challenge_ans:
                self._challenge_ok = True
                self.dismiss_btn.set_sensitive(True)
                self._chal_msg.set_text("✅ Unlocked! Hit Done to silence me.")
                lib.speak("Correct. Well done.", times=1)
            else:
                self._chal_msg.set_text("❌ Nope — try again!")

        def _on_dismiss(self, *_args):
            if not self._challenge_ok:
                self._chal_msg.set_text("🔒 Solve it first, sleepyhead!")
                return True  # block window-close too
            lib.stop_ringing(self.alarm["id"])
            lib.unduck_alarm(self.alarm["id"])  # resume paused music
            self.destroy()
            return False

        def _snooze(self, _btn, minutes: int):
            alarms = lib.load_alarms()
            for a in alarms:
                if a["id"] == self.alarm["id"]:
                    a["snooze_until"] = datetime.now().timestamp() + minutes * 60
                    a["enabled"] = True
                    a["ringing"] = False  # stop current ringing; fires again later
            lib.save_alarms(alarms)
            lib.unduck_alarm(self.alarm["id"])
            lib.send_notification("⏰ Snoozed", f"Back in {minutes} minutes.")
            self.destroy()


    class PomodoroWindow(Adw.ApplicationWindow):
        """🍅 Focus sprints with an anime cheerleader. Standalone timer."""

        def __init__(self, app: Adw.Application):
            super().__init__(application=app, title="🍅 SayAlarm Pomodoro",
                             default_width=420, default_height=560)
            self.phase = "focus"  # focus | break | long
            self.running = False
            self.done_cycles = 0
            self.remaining = 25 * 60

            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                          halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
            box.set_margin_top(24); box.set_margin_bottom(24)
            box.set_margin_start(24); box.set_margin_end(24)
            self.set_content(box)

            self.phase_lbl = Gtk.Label(label="🍅 FOCUS", css_classes=["wakeup", "rainbow"])
            box.append(self.phase_lbl)
            self.time_lbl = Gtk.Label(label="25:00", css_classes=["clock-big"])
            box.append(self.time_lbl)
            self.dots_lbl = Gtk.Label(label="○ ○ ○ ○", css_classes=["title-4"])
            box.append(self.dots_lbl)

            # Eevee cheers you on (reuse the dance frames).
            frames, durs = lib.load_beat_frames(BEAT_GIF)
            self._pomo_frames, self._pomo_durs = frames, durs
            self._pomo_idx = 0
            self._pomo_pic = None
            if frames:
                self._pomo_pic = Gtk.Picture(halign=Gtk.Align.CENTER)
                self._pomo_pic.set_filename(frames[0])
                self._pomo_pic.set_size_request(240, 136)
                box.append(self._pomo_pic)
                GLib.timeout_add(durs[0], self._pomo_advance)

            set_row = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER)
            set_row.append(Gtk.Label(label="Focus"))
            self.focus_spin = Gtk.SpinButton.new_with_range(1, 120, 1)
            self.focus_spin.set_value(25)
            set_row.append(self.focus_spin)
            set_row.append(Gtk.Label(label="Break"))
            self.break_spin = Gtk.SpinButton.new_with_range(1, 60, 1)
            self.break_spin.set_value(5)
            set_row.append(self.break_spin)
            box.append(set_row)

            btns = Gtk.Box(spacing=10, halign=Gtk.Align.CENTER)
            self.go_btn = Gtk.Button(label="▶ Start", css_classes=["suggested-action"])
            self.go_btn.connect("clicked", self._toggle)
            skip = Gtk.Button(label="⏭ Skip")
            skip.connect("clicked", lambda *_: self._finish_phase(announce=False))
            reset = Gtk.Button(label="↺ Reset")
            reset.connect("clicked", self._reset)
            for b in (self.go_btn, skip, reset):
                btns.append(b)
            box.append(btns)
            self._reset()
            GLib.timeout_add_seconds(1, self._tick)

        def _pomo_advance(self):
            if not self._pomo_frames or self._pomo_pic is None:
                return False
            self._pomo_idx = (self._pomo_idx + 1) % len(self._pomo_frames)
            self._pomo_pic.set_filename(self._pomo_frames[self._pomo_idx])
            GLib.timeout_add(self._pomo_durs[self._pomo_idx], self._pomo_advance)
            return False

        def _phase_len(self):
            if self.phase == "focus":
                return int(self.focus_spin.get_value()) * 60
            if self.phase == "break":
                return int(self.break_spin.get_value()) * 60
            return 15 * 60

        def _reset(self):
            self.running = False
            self.go_btn.set_label("▶ Start")
            self.remaining = self._phase_len()
            self._paint()

        def _toggle(self, _btn):
            self.running = not self.running
            self.go_btn.set_label("⏸ Pause" if self.running else "▶ Start")

        def _tick(self):
            if self.running:
                self.remaining -= 1
                if self.remaining <= 0:
                    self._finish_phase()
            self._paint()
            return True

        def _paint(self):
            m, s = divmod(max(0, self.remaining), 60)
            self.time_lbl.set_text(f"{m:02d}:{s:02d}")
            dots = "● " * self.done_cycles + "○ " * (4 - self.done_cycles)
            self.dots_lbl.set_text(dots.strip())

        def _finish_phase(self, announce=True):
            if self.phase == "focus":
                self.done_cycles += 1
                if announce:
                    lib.send_notification("🍅 Focus done!", "Break time — stretch! ✨")
                    lib.speak("Focus session complete. Take a break!", times=1)
                self.phase = "long" if self.done_cycles >= 4 else "break"
                if self.done_cycles >= 4:
                    self.done_cycles = 0
                self.phase_lbl.set_text("☕ LONG BREAK" if self.phase == "long"
                                        else "🌿 BREAK")
            else:
                if announce:
                    lib.send_notification("🍅 Break over", "Back to focus! 💪")
                    lib.speak("Break over. Let's focus!", times=1)
                self.phase = "focus"
                self.phase_lbl.set_text("🍅 FOCUS")
            self.remaining = self._phase_len()
            self._paint()

    class SayAlarmApp(Adw.Application):
        def __init__(self, popup_id: str | None = None, pomodoro: bool = False):
            super().__init__(application_id="dev.sayalarm.app",
                             flags=Gio.ApplicationFlags.NON_UNIQUE)
            self.popup_id = popup_id
            self.pomodoro = pomodoro

        def do_activate(self):
            load_anime_css()
            if self.pomodoro:
                win = PomodoroWindow(self)
            elif self.popup_id:
                alarm = next((a for a in lib.load_alarms()
                              if a["id"] == self.popup_id), None)
                if alarm is None:
                    alarm = {"id": self.popup_id, "hour": 0, "min": 0,
                             "note": "Time's up!"}
                win = PopupWindow(self, alarm)
            else:
                win = MainWindow(self)
            win.present()


def run_gui(popup_id: str | None = None, pomodoro: bool = False) -> int:
    app = SayAlarmApp(popup_id, pomodoro)
    # Pass a clean argv: GApplication would choke on our custom flags.
    return app.run([sys.argv[0]])


if __name__ == "__main__":
    if "--daemon" in sys.argv:
        daemon_loop()
    elif "--ring" in sys.argv:
        idx = sys.argv.index("--ring")
        rid = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else ""
        ringer_loop(rid)
    elif "--sunrise" in sys.argv:
        idx = sys.argv.index("--sunrise")
        sid = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else ""
        sunrise_loop(sid)
    elif "--pomodoro" in sys.argv:
        if not GUI_OK:
            sys.exit("GTK/Adwaita not available")
        run_gui(pomodoro=True)
    elif "--popup" in sys.argv:
        if not GUI_OK:
            sys.exit("GTK/Adwaita not available")
        idx = sys.argv.index("--popup")
        pid = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else ""
        run_gui(pid)
    else:
        if not GUI_OK:
            sys.exit("GTK/Adwaita not available")
        run_gui()
