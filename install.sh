#!/usr/bin/env bash
# Install SayAlarm: desktop launcher + always-on reminder service.
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")" && pwd)"

cp "$APP_DIR/sayalarm.desktop" ~/.local/share/applications/sayalarm.desktop
mkdir -p ~/.config/systemd/user
cp "$APP_DIR/sayalarm-daemon.service" ~/.config/systemd/user/sayalarm-daemon.service

systemctl --user daemon-reload
systemctl --user enable --now sayalarm-daemon.service
update-desktop-database ~/.local/share/applications 2>/dev/null || true

echo "SayAlarm installed. Launch it with Super+Space → SayAlarm."
systemctl --user status sayalarm-daemon.service --no-pager | head -8
