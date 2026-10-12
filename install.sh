#!/usr/bin/env bash
# Install SayAlarm: desktop launcher + always-on reminder service.
# Works from any clone location: @@SAYALARM_DIR@@ is stamped with this
# repo's real path at install time.
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")" && pwd)"

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
