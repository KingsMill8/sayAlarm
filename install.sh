#!/usr/bin/env bash
# Install SayAlarm: desktop launcher + always-on reminder service.
# Works from any clone location: @@SAYALARM_DIR@@ is stamped with this
# repo's real path at install time.
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")" && pwd)"

# --- dependency check (hard fail only on the must-haves) ---
missing=()
for cmd in python3 notify-send systemctl; do
  command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd")
done
python3 -c "import gi; gi.require_version('Gtk','4.0'); gi.require_version('Adw','1')" 2>/dev/null \
  || missing+=("python-gobject+gtk4+libadwaita")
if [ "${#missing[@]}" -gt 0 ]; then
  echo "Missing required: ${missing[*]}" >&2
  echo "Arch: sudo pacman -S python-gobject gtk4 libadwaita libnotify" >&2
  echo "Debian/Ubuntu: sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 libnotify-bin" >&2
  exit 1
fi
# Soft deps (features degrade gracefully without them — installer only warns).
for cmd in espeak-ng mpv ffmpeg brightnessctl playerctl arecord curl; do
  command -v "$cmd" >/dev/null 2>&1 || echo "Note: '$cmd' not found — related feature will be skipped gracefully."
done

sed "s|@@SAYALARM_DIR@@|$APP_DIR|g" "$APP_DIR/sayalarm.desktop" \
  > ~/.local/share/applications/sayalarm.desktop
mkdir -p ~/.config/systemd/user
sed "s|@@SAYALARM_DIR@@|$APP_DIR|g" "$APP_DIR/sayalarm-daemon.service" \
  > ~/.config/systemd/user/sayalarm-daemon.service

systemctl --user daemon-reload
systemctl --user enable --now sayalarm-daemon.service
update-desktop-database ~/.local/share/applications 2>/dev/null || true

echo "SayAlarm installed. Launch it with Super+Space → SayAlarm."
systemctl --user status sayalarm-daemon.service --no-pager | head -8
