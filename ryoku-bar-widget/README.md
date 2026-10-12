# SayAlarm bar widget

Next SayAlarm on the Ryoku bar: `⏰ 07:30 · in 3h 12m`. Clicking the glyph
opens a panel with the note, the countdown, an OPEN APP button and REFRESH.

## What it runs

- `bin/next-alarm` (python3): polled every 30s by `service/Main.qml`. Reads
  `~/.local/share/sayalarm/alarms.json` through the desktop app's own
  `alarm_lib`, prints one JSON line. Never exits non-zero.
- `bin/open-sayalarm`: runs only on the panel's explicit OPEN APP click and
  launches the SayAlarm desktop app.

## What it reads and writes

- Reads: the alarm store above (read-only) + its own `pluginSettings`.
- Writes: nothing. No state files, no network, no privileged actions.

## Capabilities

- Hosts: `topbarGlyph` only. External command: `python3` (declared in
  `dependencies.commands`). No network, no pkexec, no secrets, no binaries.
