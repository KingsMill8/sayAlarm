pragma ComponentBehavior: Bound

import QtQuick
import Quickshell.Io

// SayAlarm service: polls bin/next-alarm for the next firing alarm and
// exposes it (nextTime/nextNote/nextWhen/hasAlarm) to the widget + panel.
// The script reuses the desktop app's own alarm logic, so the bar always
// agrees with the app. Failures keep last good values (never blank).
Item {
    id: root

    property var pluginApi
    readonly property var settings: pluginApi ? pluginApi.pluginSettings : null
    // The host wires pluginApi after load; gate the first poll on it.
    readonly property bool ready: !!(pluginApi && pluginApi.pluginDir && pluginApi.pluginDir.length > 0)

    function _bool(k, d) {
        if (!settings || settings[k] === undefined || settings[k] === null)
            return d;
        return settings[k] === true || settings[k] === "true";
    }
    readonly property bool showCountdown: _bool("showCountdown", true)

    property string nextTime: ""
    property string nextNote: ""
    property string nextWhen: ""
    property bool hasAlarm: false

    function cmdPath() { return (pluginApi ? pluginApi.pluginDir : "") + "/bin/next-alarm"; }

    function refresh() {
        if (!ready || fetchProc.running)
            return;
        _stdout = "";
        fetchProc.command = [cmdPath()];
        fetchProc.running = true;
    }

    property string _stdout: ""
    function _finish() {
        var line = _stdout.split("\n").filter(function (l) { return l.trim().length > 0; }).pop() || "";
        if (line.length === 0)
            return;
        var d;
        try {
            d = JSON.parse(line);
        } catch (e) {
            return;
        }
        if (d.none) {
            hasAlarm = false;
            nextTime = "";
            nextNote = "";
            nextWhen = "";
            return;
        }
        hasAlarm = true;
        nextTime = String(d.time || "");
        nextNote = String(d.note || "");
        nextWhen = String(d.when || "");
    }

    Process {
        id: fetchProc
        stdout: StdioCollector { onStreamFinished: root._stdout = text }
        onExited: root._finish()
    }

    onReadyChanged: if (ready) refresh();

    Timer {
        interval: 30000
        running: root.ready
        repeat: true
        onTriggered: root.refresh()
    }
}
