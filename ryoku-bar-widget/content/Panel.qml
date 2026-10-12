import QtQuick
import Quickshell.Io
import Ryoku.PluginKit.Singletons

// SayAlarm bar panel: the next alarm's time, note and countdown, plus
// explicit-click actions (open the app, refresh now).
Item {
    id: root

    property var pluginApi
    property string density: "full"
    property real s: 1
    property real widthBudget: 320
    property bool active: false

    readonly property var service: pluginApi ? pluginApi.mainInstance : null
    readonly property bool hasAlarm: service ? service.hasAlarm : false

    function openApp() {
        if (!pluginApi || !pluginApi.pluginDir)
            return;
        openProc.command = [pluginApi.pluginDir + "/bin/open-sayalarm"];
        openProc.running = true;
    }

    Process {
        id: openProc
    }

    implicitWidth: root.widthBudget
    implicitHeight: col.implicitHeight + 24 * root.s

    Column {
        id: col
        x: 12 * root.s
        y: 12 * root.s
        width: root.width - 24 * root.s
        spacing: 10 * root.s

        Text {
            text: "⏰ SayAlarm"
            color: Theme.bright
            font.family: Theme.display
            font.pixelSize: 16 * root.s
        }

        Text {
            text: root.hasAlarm ? root.service.nextTime : "—"
            color: Theme.accent
            font.family: Theme.display
            font.pixelSize: 30 * root.s
        }

        Text {
            text: root.hasAlarm ? root.service.nextNote : qsTr("No alarms set")
            color: Theme.bright
            font.family: Theme.font
            font.pixelSize: 14 * root.s
            wrapMode: Text.WordWrap
            width: parent.width
        }

        Text {
            visible: root.hasAlarm
            text: root.hasAlarm ? root.service.nextWhen : ""
            color: Theme.gold
            font.family: Theme.font
            font.pixelSize: 13 * root.s
        }

        Row {
            spacing: 8 * root.s

            Rectangle {
                width: openLabel.implicitWidth + 24 * root.s
                height: openLabel.implicitHeight + 12 * root.s
                radius: Theme.radius
                color: openArea.pressed ? Theme.vermDeep : Theme.accent

                Text {
                    id: openLabel
                    anchors.centerIn: parent
                    text: qsTr("OPEN APP")
                    color: Theme.cardBot
                    font.family: Theme.font
                    font.pixelSize: 12 * root.s
                }

                MouseArea {
                    id: openArea
                    anchors.fill: parent
                    onClicked: root.openApp()
                }
            }

            Rectangle {
                width: refreshLabel.implicitWidth + 24 * root.s
                height: refreshLabel.implicitHeight + 12 * root.s
                radius: Theme.radius
                color: Theme.cardTop
                border.color: Theme.dim
                border.width: 1

                Text {
                    id: refreshLabel
                    anchors.centerIn: parent
                    text: qsTr("REFRESH")
                    color: Theme.bright
                    font.family: Theme.font
                    font.pixelSize: 12 * root.s
                }

                MouseArea {
                    anchors.fill: parent
                    onClicked: if (root.service) root.service.refresh()
                }
            }
        }
    }
}
