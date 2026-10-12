import QtQuick
import Ryoku.PluginKit.Singletons

// SayAlarm bar glyph: ⏰ + next alarm time (and countdown). A left click
// toggles the panel; the click never mutates anything.
Item {
    id: root

    property var pluginApi
    property var screen
    property bool active: false
    property string density: "glyph"
    property real s: 1
    property real widthBudget: 0

    readonly property var service: pluginApi ? pluginApi.mainInstance : null
    readonly property bool hasAlarm: service ? service.hasAlarm : false
    readonly property string label: {
        if (!service || !hasAlarm)
            return qsTr("no alarms");
        var t = service.nextTime;
        if (service.showCountdown && service.nextWhen.length > 0)
            return t + " · " + service.nextWhen;
        return t;
    }

    implicitWidth: row.implicitWidth
    implicitHeight: Math.max(row.implicitHeight, 18 * root.s)

    Row {
        id: row
        anchors.verticalCenter: parent.verticalCenter
        spacing: 6 * root.s

        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: "⏰"
            font.pixelSize: 13 * root.s
        }

        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: root.label
            color: root.hasAlarm ? Theme.bright : Theme.dim
            font.family: Theme.font
            font.pixelSize: 13 * root.s
            elide: Text.ElideRight
            width: root.widthBudget > 0 ? Math.min(implicitWidth, root.widthBudget) : implicitWidth
        }
    }

    MouseArea {
        anchors.fill: parent
        onClicked: if (root.pluginApi) root.pluginApi.togglePanel()
    }
}
