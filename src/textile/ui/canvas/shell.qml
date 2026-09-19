import QtQuick
import Quickshell
import Quickshell.Io

ShellRoot {
    id: root

    // Central state & expression controller
    QtObject {
        id: stateController

        property string currentMood: "neutral"
        property string currentExpression: "neutral"
        property bool isTalking: false
        property bool isListening: false
        property bool isToolExecuting: false

        // Extended Rich Color Palettes per mood (Catppuccin Mocha + Synthwave inspired)
        readonly property var moodColors: ({
            "neutral":      { "bg": "#181825", "feat": "#fab387", "gem": "#89b4fa", "aura": "#313244", "blush": "#f38ba8" }, // Peach face with Sapphire Gem
            "happy":        { "bg": "#181825", "feat": "#a6e3a1", "gem": "#f5c2e7", "aura": "#2d4a3e", "blush": "#f5c2e7" }, // Mint face with Rose Gem
            "excited":      { "bg": "#1e1e2e", "feat": "#f5c2e7", "gem": "#94e2d5", "aura": "#583759", "blush": "#f38ba8" }, // Pink face with Teal Gem
            "celebrating":  { "bg": "#1e1e2e", "feat": "#f9e2af", "gem": "#cba6f7", "aura": "#5e4b2d", "blush": "#f5c2e7" }, // Gold face with Purple Gem
            "thinking":     { "bg": "#181825", "feat": "#89b4fa", "gem": "#fab387", "aura": "#2b3b59", "blush": "#b4befe" }, // Blue face with Peach Gem
            "focused":      { "bg": "#11111b", "feat": "#74c7ec", "gem": "#fab387", "aura": "#1b3b4b", "blush": "#89dceb" }, // Cyan face with Amber Gem
            "listening":    { "bg": "#181825", "feat": "#94e2d5", "gem": "#f38ba8", "aura": "#244d47", "blush": "#a6e3a1" }, // Teal face with Coral Gem
            "curious":      { "bg": "#181825", "feat": "#cba6f7", "gem": "#f9e2af", "aura": "#3f2d57", "blush": "#f5c2e7" }, // Purple face with Gold Gem
            "calm":         { "bg": "#181825", "feat": "#b4befe", "gem": "#fab387", "aura": "#283050", "blush": "#cba6f7" }, // Lavender face with Peach Gem
            "shy":          { "bg": "#181825", "feat": "#eba0ac", "gem": "#89dceb", "aura": "#4a2d36", "blush": "#f38ba8" }, // Blossom face with Cyan Gem
            "mischievous":  { "bg": "#1e1e2e", "feat": "#cba6f7", "gem": "#f9e2af", "aura": "#4d255a", "blush": "#eba0ac" }, // Plum face with Gold Gem
            "confused":     { "bg": "#181825", "feat": "#eba0ac", "gem": "#94e2d5", "aura": "#3d2d38", "blush": "#f5c2e7" }, // Flamingo face with Teal Gem
            "surprised":    { "bg": "#181825", "feat": "#f9e2af", "gem": "#89b4fa", "aura": "#4f4325", "blush": "#fab387" }, // Amber face with Blue Gem
            "alert":        { "bg": "#1e141a", "feat": "#fab387", "gem": "#89dceb", "aura": "#5c331e", "blush": "#f38ba8" }, // Tangerine face with Cyan Gem
            "sleepy":       { "bg": "#11111b", "feat": "#6c7086", "gem": "#b4befe", "aura": "#181825", "blush": "#45475a" }, // Slate face with Lavender Gem
            "error":        { "bg": "#1e141a", "feat": "#f38ba8", "gem": "#94e2d5", "aura": "#541b2b", "blush": "#eba0ac" }, // Crimson face with Cyan Gem
            "glitch":       { "bg": "#11111b", "feat": "#89dceb", "gem": "#f5c2e7", "aura": "#4d1a3a", "blush": "#f38ba8" }  // Neon Cyan face with Pink Gem
        })

        function applyMood(mood) {
            var m = mood.toLowerCase().trim();
            if (moodColors[m]) {
                currentMood = m;
                canvasWindow.featureColor = moodColors[m].feat;
                canvasWindow.gemColor = moodColors[m].gem;
                canvasWindow.backgroundColor = moodColors[m].bg;
                canvasWindow.auraColor = moodColors[m].aura;
                canvasWindow.blushColor = moodColors[m].blush;
            } else {
                currentMood = m;
            }
            return "OK:" + currentMood;
        }

        function applyTalking(talking) {
            var val = false;
            if (typeof talking === "string") {
                val = (talking.toLowerCase() === "true" || talking === "1");
            } else {
                val = Boolean(talking);
            }
            isTalking = val;
            if (!val) {
                talkingTimer.mouthPhase = 0;
            }
            return "OK:talking=" + isTalking;
        }

        function applyListening(listening) {
            if (typeof listening === "string") {
                isListening = (listening.toLowerCase() === "true" || listening === "1");
            } else {
                isListening = Boolean(listening);
            }
            return "OK:listening=" + isListening;
        }

        function applyToolExecuting(executing) {
            var val = false;
            if (typeof executing === "string") {
                val = (executing.toLowerCase() === "true" || executing === "1");
            } else {
                val = Boolean(executing);
            }
            isToolExecuting = val;
            if (val) {
                rippleWaveAnimation.restart();
            }
            return "OK:toolExecuting=" + isToolExecuting;
        }
    }

    IpcHandler {
        target: "canvas"

        function setMood(mood: string): string {
            return stateController.applyMood(mood);
        }

        function setExpression(expression: string): string {
            stateController.currentExpression = expression;
            return "OK:" + expression;
        }

        function setTalking(talking: string): string {
            return stateController.applyTalking(talking);
        }

        function setListening(listening: string): string {
            return stateController.applyListening(listening);
        }

        function setToolExecuting(executing: string): string {
            return stateController.applyToolExecuting(executing);
        }

        function triggerRipple(): string {
            rippleWaveAnimation.restart();
            return "OK:ripple";
        }

        function setGaze(x: real, y: real): string {
            gazeTracker.manualGazeX = x;
            gazeTracker.manualGazeY = y;
            gazeTracker.useManualGaze = true;
            return "OK:gaze";
        }

        function resetGaze(): string {
            gazeTracker.useManualGaze = false;
            return "OK:resetGaze";
        }

        function setColor(featureColor: string, bgColor: string): string {
            if (featureColor) canvasWindow.featureColor = featureColor;
            if (bgColor) canvasWindow.backgroundColor = bgColor;
            return "OK:colors";
        }

        function getMood(): string {
            return stateController.currentMood;
        }

        function getState(): string {
            return JSON.stringify({
                "mood": stateController.currentMood,
                "expression": stateController.currentExpression,
                "is_talking": stateController.isTalking,
                "is_listening": stateController.isListening,
                "is_tool_executing": stateController.isToolExecuting,
                "feature_color": canvasWindow.featureColor.toString(),
                "bg_color": canvasWindow.backgroundColor.toString(),
                "aura_color": canvasWindow.auraColor.toString()
            });
        }

        function quit(): string {
            Qt.quit();
            return "OK:quit";
        }
    }

    FloatingWindow {
        id: canvasWindow

        title: "Textile Canvas"
        visible: true

        implicitWidth: 640
        implicitHeight: 480

        property color backgroundColor: "#181825"
        property color featureColor: "#fab387"
        property color gemColor: "#89b4fa"
        property color auraColor: "#313244"
        property color blushColor: "#f38ba8"

        property bool isBlinking: false
        property real yOffset: 0.0
        property real shakeOffset: 0.0
        property real clickScale: 1.0

        Behavior on featureColor { ColorAnimation { duration: 340; easing.type: Easing.InOutQuad } }
        Behavior on gemColor { ColorAnimation { duration: 340; easing.type: Easing.InOutQuad } }
        Behavior on backgroundColor { ColorAnimation { duration: 340; easing.type: Easing.InOutQuad } }
        Behavior on auraColor { ColorAnimation { duration: 340; easing.type: Easing.InOutQuad } }
        Behavior on blushColor { ColorAnimation { duration: 340; easing.type: Easing.InOutQuad } }

        onVisibleChanged: {
            if (!visible) {
                Qt.quit();
            }
        }

        Component.onDestruction: {
            Qt.quit();
        }

        Shortcut { sequence: "Esc"; onActivated: Qt.quit() }
        Shortcut { sequence: "q"; onActivated: Qt.quit() }

        // Dynamic Blink Timer (Mood aware)
        Timer {
            id: blinkTimer
            interval: {
                if (stateController.currentMood === "sleepy") return 1400;
                if (stateController.currentMood === "excited" || stateController.currentMood === "celebrating") return 1900;
                if (stateController.currentMood === "focused") return 4200; // Unblinking focus
                return Math.floor(Math.random() * 2500) + 2200;
            }
            running: true
            repeat: true
            onTriggered: {
                if (stateController.currentMood !== "surprised" && stateController.currentMood !== "alert") {
                    canvasWindow.isBlinking = true;
                    blinkCloseTimer.start();
                }
            }
        }

        Timer {
            id: blinkCloseTimer
            interval: stateController.currentMood === "sleepy" ? 380 : 150
            running: false
            repeat: false
            onTriggered: {
                canvasWindow.isBlinking = false;
            }
        }

        // Multi-frame natural lip sync timer
        Timer {
            id: talkingTimer
            interval: {
                var cadence = [85, 110, 75, 95];
                return cadence[mouthPhase] || 85;
            }
            running: stateController.isTalking
            repeat: true
            property int mouthPhase: 0
            onTriggered: {
                mouthPhase = (mouthPhase + 1) % 4;
            }
        }

        // Error & Glitch Shake animation
        SequentialAnimation on shakeOffset {
            running: stateController.currentMood === "error" || stateController.currentMood === "glitch"
            loops: Animation.Infinite
            NumberAnimation { to: stateController.currentMood === "glitch" ? 6.0 : 4.0; duration: 50; easing.type: Easing.Linear }
            NumberAnimation { to: stateController.currentMood === "glitch" ? -6.0 : -4.0; duration: 50; easing.type: Easing.Linear }
            NumberAnimation { to: 0.0; duration: 50; easing.type: Easing.Linear }
            PauseAnimation { duration: stateController.currentMood === "glitch" ? 250 : 400 }
        }

        // Ambient Organic Breathing / Floating Animation
        SequentialAnimation on yOffset {
            loops: Animation.Infinite
            running: true
            NumberAnimation {
                to: {
                    if (stateController.currentMood === "excited" || stateController.currentMood === "celebrating") return 16;
                    if (stateController.currentMood === "surprised" || stateController.currentMood === "alert") return -14;
                    if (stateController.currentMood === "sleepy" || stateController.currentMood === "calm") return 4;
                    if (stateController.currentMood === "error") return 4;
                    return 8;
                }
                duration: {
                    if (stateController.currentMood === "excited" || stateController.currentMood === "celebrating") return 650;
                    if (stateController.currentMood === "sleepy" || stateController.currentMood === "calm") return 3200;
                    if (stateController.currentMood === "thinking" || stateController.currentMood === "focused") return 2000;
                    return 1500;
                }
                easing.type: Easing.InOutSine
            }
            NumberAnimation {
                to: {
                    if (stateController.currentMood === "excited" || stateController.currentMood === "celebrating") return -16;
                    if (stateController.currentMood === "surprised" || stateController.currentMood === "alert") return 8;
                    if (stateController.currentMood === "sleepy" || stateController.currentMood === "calm") return -4;
                    if (stateController.currentMood === "error") return -4;
                    return -8;
                }
                duration: {
                    if (stateController.currentMood === "excited" || stateController.currentMood === "celebrating") return 650;
                    if (stateController.currentMood === "sleepy" || stateController.currentMood === "calm") return 3200;
                    if (stateController.currentMood === "thinking" || stateController.currentMood === "focused") return 2000;
                    return 1500;
                }
                easing.type: Easing.InOutSine
            }
        }

        Rectangle {
            id: backgroundCanvas
            anchors.fill: parent
            color: canvasWindow.backgroundColor

            MouseArea {
                id: gazeTracker
                anchors.fill: parent
                hoverEnabled: true

                property bool useManualGaze: false
                property real manualGazeX: 0.0
                property real manualGazeY: 0.0

                property real mouseGazeX: ((mouseX - width / 2) / (width / 2)) * 16.0
                property real mouseGazeY: ((mouseY - height / 2) / (height / 2)) * 12.0

                // Biological Micro-Saccades (Subtle subconscious eye fixations)
                property real saccadeX: 0.0
                property real saccadeY: 0.0
                Behavior on saccadeX { NumberAnimation { duration: 120; easing.type: Easing.OutQuad } }
                Behavior on saccadeY { NumberAnimation { duration: 120; easing.type: Easing.OutQuad } }

                Timer {
                    id: saccadeTimer
                    interval: 2500
                    running: true
                    repeat: true
                    onTriggered: {
                        gazeTracker.saccadeX = (Math.random() * 2.0 - 1.0) * 0.8;
                        gazeTracker.saccadeY = (Math.random() * 2.0 - 1.0) * 0.5;
                        interval = Math.floor(Math.random() * 1500) + 2000;
                    }
                }

                readonly property real baseGazeX: {
                    if (stateController.currentMood === "thinking") return 9.0;  // Looks up-right
                    if (stateController.currentMood === "shy") return 2.5;       // Looks down
                    if (useManualGaze) return manualGazeX;
                    return mouseGazeX;
                }
                readonly property real baseGazeY: {
                    if (stateController.currentMood === "thinking") return -8.0; // Looks up
                    if (stateController.currentMood === "shy") return 8.0;       // Looks down
                    if (useManualGaze) return manualGazeY;
                    return mouseGazeY;
                }

                readonly property real targetGazeX: baseGazeX + saccadeX
                readonly property real targetGazeY: baseGazeY + saccadeY

                onClicked: {
                    // Delightful click reaction: interactive elastic bounce!
                    clickBounce.restart();
                }
            }

            SequentialAnimation {
                id: clickBounce
                NumberAnimation { target: canvasWindow; property: "clickScale"; to: 0.82; duration: 80; easing.type: Easing.OutQuad }
                NumberAnimation { target: canvasWindow; property: "clickScale"; to: 1.16; duration: 160; easing.type: Easing.OutBack; easing.overshoot: 1.6 }
                NumberAnimation { target: canvasWindow; property: "clickScale"; to: 0.96; duration: 90; easing.type: Easing.InOutQuad }
                NumberAnimation { target: canvasWindow; property: "clickScale"; to: 1.0; duration: 80; easing.type: Easing.OutQuad }
            }

            Item {
                id: faceContainer
                width: parent.width * 0.8
                height: parent.height * 0.7
                anchors.centerIn: parent
                anchors.verticalCenterOffset: canvasWindow.yOffset
                anchors.horizontalCenterOffset: canvasWindow.shakeOffset
                scale: canvasWindow.clickScale

                // Head tilt per mood & subtle gaze orientation
                rotation: {
                    if (stateController.currentMood === "curious") return 9.5;
                    if (stateController.currentMood === "mischievous") return -8.0;
                    if (stateController.currentMood === "confused") return -8.5;
                    if (stateController.currentMood === "thinking") return 4.5;
                    if (stateController.currentMood === "happy" || stateController.currentMood === "celebrating") return 2.5;
                    if (stateController.currentMood === "shy") return -3.0;
                    return (gazeTracker.baseGazeX / 16.0) * 3.5;
                }
                Behavior on rotation { NumberAnimation { duration: 250; easing.type: Easing.OutQuad } }

                // ==================== CHEEK BLUSHES ====================
                Row {
                    id: blushRow
                    anchors.top: eyesRow.bottom
                    anchors.topMargin: parent.height * 0.04
                    anchors.horizontalCenter: parent.horizontalCenter
                    spacing: parent.width * 0.52

                    readonly property bool shouldBlush: {
                        var m = stateController.currentMood;
                        return (m === "happy" || m === "excited" || m === "celebrating" || m === "shy" || m === "mischievous" || stateController.currentExpression === "blush");
                    }

                    Rectangle {
                        id: leftBlush
                        width: parent.parent.width * 0.10
                        height: width * 0.55
                        radius: height / 2
                        color: canvasWindow.blushColor
                        opacity: blushRow.shouldBlush ? (stateController.currentMood === "shy" ? 0.75 : 0.45) : 0.0
                        Behavior on opacity { NumberAnimation { duration: 300; easing.type: Easing.InOutQuad } }
                    }

                    Rectangle {
                        id: rightBlush
                        width: parent.parent.width * 0.10
                        height: width * 0.55
                        radius: height / 2
                        color: canvasWindow.blushColor
                        opacity: blushRow.shouldBlush ? (stateController.currentMood === "shy" ? 0.75 : 0.45) : 0.0
                        Behavior on opacity { NumberAnimation { duration: 300; easing.type: Easing.InOutQuad } }
                    }
                }

                // ==================== FOREHEAD CORE GEM & DYNAMIC SINGLE-SHOT WATER RIPPLE ====================
                Item {
                    id: foreheadGem
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.top: parent.top
                    anchors.topMargin: parent.height * 0.04
                    width: 24
                    height: 24

                    // Layer 1: Primary Soft Water Wave (Emitted in complementary Gem Color)
                    Rectangle {
                        id: ripple1
                        anchors.centerIn: parent
                        width: 20
                        height: 20
                        radius: 10
                        color: canvasWindow.gemColor
                        border.color: canvasWindow.gemColor
                        border.width: 1.0
                        opacity: 0.0
                        scale: 1.0
                    }

                    // Layer 2: Secondary Harmonic Wave (Staggered 260ms)
                    Rectangle {
                        id: ripple2
                        anchors.centerIn: parent
                        width: 20
                        height: 20
                        radius: 10
                        color: canvasWindow.gemColor
                        border.color: canvasWindow.gemColor
                        border.width: 0.8
                        opacity: 0.0
                        scale: 1.0
                    }

                    // Layer 3: Tertiary Harmonic Echo (Staggered 520ms)
                    Rectangle {
                        id: ripple3
                        anchors.centerIn: parent
                        width: 20
                        height: 20
                        radius: 10
                        color: canvasWindow.gemColor
                        border.color: canvasWindow.gemColor
                        border.width: 0.5
                        opacity: 0.0
                        scale: 1.0
                    }

                    // Standalone Single-Shot Water Ripple Animation (One emission per tool call)
                    ParallelAnimation {
                        id: rippleWaveAnimation
                        running: false
                        loops: 1

                        onStopped: {
                            ripple1.scale = 1.0;
                            ripple1.opacity = 0.0;
                            ripple2.scale = 1.0;
                            ripple2.opacity = 0.0;
                            ripple3.scale = 1.0;
                            ripple3.opacity = 0.0;
                            gemAssembly.scale = 1.0;
                        }

                        // Synchronized, low-pacing gentle gem assembly breath/pulse
                        SequentialAnimation {
                            NumberAnimation { target: gemAssembly; property: "scale"; from: 1.0; to: 1.30; duration: 420; easing.type: Easing.OutSine }
                            NumberAnimation { target: gemAssembly; property: "scale"; from: 1.30; to: 1.0; duration: 780; easing.type: Easing.InOutSine }
                        }

                        // Wave 1: Primary Crest & Wash (Soft Subtle Opacity)
                        ParallelAnimation {
                            NumberAnimation { target: ripple1; property: "scale"; from: 1.0; to: 85.0; duration: 1750; easing.type: Easing.OutCubic }
                            SequentialAnimation {
                                NumberAnimation { target: ripple1; property: "opacity"; from: 0.0; to: 0.18; duration: 200; easing.type: Easing.OutQuad }
                                NumberAnimation { target: ripple1; property: "opacity"; from: 0.18; to: 0.0; duration: 1550; easing.type: Easing.InQuad }
                            }
                        }

                        // Wave 2: Secondary Harmonic
                        SequentialAnimation {
                            PauseAnimation { duration: 260 }
                            ParallelAnimation {
                                NumberAnimation { target: ripple2; property: "scale"; from: 1.0; to: 80.0; duration: 1700; easing.type: Easing.OutCubic }
                                SequentialAnimation {
                                    NumberAnimation { target: ripple2; property: "opacity"; from: 0.0; to: 0.11; duration: 220; easing.type: Easing.OutQuad }
                                    NumberAnimation { target: ripple2; property: "opacity"; from: 0.11; to: 0.0; duration: 1480; easing.type: Easing.InQuad }
                                }
                            }
                        }

                        // Wave 3: Tertiary Echo
                        SequentialAnimation {
                            PauseAnimation { duration: 520 }
                            ParallelAnimation {
                                NumberAnimation { target: ripple3; property: "scale"; from: 1.0; to: 75.0; duration: 1650; easing.type: Easing.OutCubic }
                                SequentialAnimation {
                                    NumberAnimation { target: ripple3; property: "opacity"; from: 0.0; to: 0.06; duration: 240; easing.type: Easing.OutQuad }
                                    NumberAnimation { target: ripple3; property: "opacity"; from: 0.06; to: 0.0; duration: 1410; easing.type: Easing.InQuad }
                                }
                            }
                        }
                    }

                    // ==================== GLOWING FOREHEAD GEMSTONE ASSEMBLY ====================
                    // Unified concentric container: guaranteed pixel-perfect concentric centering & synchronized scaling
                    Item {
                        id: gemAssembly
                        anchors.centerIn: parent
                        width: 28
                        height: 28
                        transformOrigin: Item.Center
                        scale: 1.0

                        // Outer Soft Ambient Aura Glow
                        Rectangle {
                            id: gemAuraOuter
                            anchors.centerIn: parent
                            width: 26
                            height: 26
                            radius: 13
                            color: canvasWindow.gemColor
                            opacity: foreheadDot.opacity * 0.20
                            Behavior on opacity { NumberAnimation { duration: 250 } }
                        }

                        // Mid Radiant Halo Glow
                        Rectangle {
                            id: gemGlowMid
                            anchors.centerIn: parent
                            width: 18
                            height: 18
                            radius: 9
                            color: canvasWindow.gemColor
                            opacity: foreheadDot.opacity * 0.45
                            Behavior on opacity { NumberAnimation { duration: 250 } }
                        }

                        // Central Glowing Forehead Core Gemstone
                        Rectangle {
                            id: foreheadDot
                            anchors.centerIn: parent
                            width: 10
                            height: 10
                            radius: 5
                            color: canvasWindow.gemColor

                            opacity: {
                                if (stateController.isToolExecuting) return 1.0;
                                if (stateController.currentMood === "sleepy") return 0.25;
                                if (stateController.currentMood === "focused" || stateController.currentMood === "celebrating") return 0.95;
                                return 0.70;
                            }
                            Behavior on opacity { NumberAnimation { duration: 250 } }

                            // Specular Gem Crystal Catchlight
                            Rectangle {
                                id: gemSpecular
                                width: 3
                                height: 3
                                radius: 1.5
                                color: "#ffffff"
                                anchors.top: parent.top
                                anchors.topMargin: 2
                                anchors.left: parent.left
                                anchors.leftMargin: 2
                                opacity: 0.85
                            }
                        }
                    }
                }

                // ==================== EYES ROW ====================
                Row {
                    id: eyesRow
                    anchors.top: parent.top
                    anchors.topMargin: parent.height * 0.15
                    anchors.horizontalCenter: parent.horizontalCenter
                    spacing: parent.width * 0.45

                    // ---------- LEFT EYE FRAME ----------
                    Item {
                        id: leftEyeFrame
                        width: parent.parent.parent.width * 0.13
                        height: width

                        // Left Eyebrow / Angle Rotation
                        rotation: {
                            if (stateController.currentMood === "happy" || stateController.currentMood === "celebrating") return -14;
                            if (stateController.currentMood === "error" || stateController.currentMood === "alert") return 24; // Slanted down inside
                            if (stateController.currentMood === "curious" || stateController.currentMood === "mischievous") return -14; // Arched high
                            if (stateController.currentMood === "confused") return 16;
                            if (stateController.currentMood === "sleepy" || stateController.currentMood === "calm") return -4;
                            if (stateController.currentMood === "focused") return 8;
                            return 0;
                        }
                        Behavior on rotation { NumberAnimation { duration: 200; easing.type: Easing.InOutQuad } }

                        // Eye vertical position offset
                        y: {
                            if (stateController.currentMood === "curious" || stateController.currentMood === "mischievous") return -11;
                            if (stateController.currentMood === "thinking") return -7;
                            if (stateController.currentMood === "shy") return 5;
                            return 0;
                        }
                        Behavior on y { NumberAnimation { duration: 200; easing.type: Easing.OutQuad } }

                        Rectangle {
                            id: leftEye
                            anchors.centerIn: parent
                            anchors.horizontalCenterOffset: gazeTracker.targetGazeX
                            anchors.verticalCenterOffset: gazeTracker.targetGazeY

                            color: canvasWindow.featureColor

                            // Morphing Width
                            width: {
                                if (stateController.currentMood === "happy" || stateController.currentMood === "celebrating") return parent.width * 1.15;
                                if (stateController.currentMood === "sleepy" || stateController.currentMood === "calm") return parent.width * 1.15;
                                if (stateController.currentMood === "surprised" || stateController.currentMood === "alert") return parent.width * 1.38;
                                if (stateController.currentMood === "excited") return parent.width * 1.25;
                                if (stateController.currentMood === "thinking" || stateController.currentMood === "focused") return parent.width * 0.92;
                                return parent.width;
                            }

                            // Morphing Height
                            height: {
                                if (canvasWindow.isBlinking || stateController.currentExpression === "wink_left") return parent.height * 0.08;
                                if (stateController.currentMood === "sleepy") return parent.height * 0.16; // Drowsy slit
                                if (stateController.currentMood === "calm" || stateController.currentMood === "shy") return parent.height * 0.42;
                                if (stateController.currentMood === "happy" || stateController.currentMood === "celebrating") return parent.height * 0.58; // Smiling crescent
                                if (stateController.currentMood === "error" || stateController.currentMood === "alert") return parent.height * 0.65; // Sharp glare
                                if (stateController.currentMood === "surprised") return parent.height * 1.38; // Huge shocked eye
                                if (stateController.currentMood === "excited") return parent.height * 1.25;
                                if (stateController.currentMood === "listening") return parent.height * 1.18;
                                if (stateController.currentMood === "curious" || stateController.currentMood === "mischievous") return parent.height * 1.12;
                                if (stateController.currentMood === "focused") return parent.height * 0.75;
                                return parent.height;
                            }

                            radius: {
                                if (stateController.currentMood === "happy" || stateController.currentMood === "celebrating") return height * 0.45;
                                if (stateController.currentMood === "sleepy" || stateController.currentMood === "calm") return height / 2;
                                return width / 2;
                            }

                            Behavior on width { NumberAnimation { duration: 140; easing.type: Easing.InOutQuad } }
                            Behavior on height { NumberAnimation { duration: 140; easing.type: Easing.InOutQuad } }
                            Behavior on radius { NumberAnimation { duration: 140; easing.type: Easing.InOutQuad } }
                            Behavior on anchors.horizontalCenterOffset { NumberAnimation { duration: 80; easing.type: Easing.OutQuad } }
                            Behavior on anchors.verticalCenterOffset { NumberAnimation { duration: 80; easing.type: Easing.OutQuad } }

                            // Specular Catchlight (Eye sparkle)
                            Rectangle {
                                id: leftCatchlight
                                width: parent.width * 0.32
                                height: width
                                radius: width / 2
                                color: "#ffffff"
                                anchors.top: parent.top
                                anchors.topMargin: parent.height * 0.16
                                anchors.left: parent.left
                                anchors.leftMargin: parent.width * 0.22
                                opacity: {
                                    if (canvasWindow.isBlinking || stateController.currentMood === "sleepy") return 0.0;
                                    if (stateController.currentMood === "celebrating" || stateController.currentMood === "excited") return 0.95;
                                    if (stateController.currentMood === "happy" || stateController.currentMood === "curious") return 0.85;
                                    return 0.65;
                                }
                                Behavior on opacity { NumberAnimation { duration: 150 } }
                            }
                        }
                    }

                    // ---------- RIGHT EYE FRAME ----------
                    Item {
                        id: rightEyeFrame
                        width: parent.parent.parent.width * 0.13
                        height: width

                        // Right Eyebrow / Angle Rotation
                        rotation: {
                            if (stateController.currentMood === "happy" || stateController.currentMood === "celebrating") return 14;
                            if (stateController.currentMood === "error" || stateController.currentMood === "alert") return -24; // Slanted down inside
                            if (stateController.currentMood === "curious") return 12;
                            if (stateController.currentMood === "mischievous") return 22; // Very smug arch
                            if (stateController.currentMood === "confused") return -18;  // Raised quizzical
                            if (stateController.currentMood === "sleepy" || stateController.currentMood === "calm") return 4;
                            if (stateController.currentMood === "focused") return -8;
                            return 0;
                        }
                        Behavior on rotation { NumberAnimation { duration: 200; easing.type: Easing.InOutQuad } }

                        // Eye vertical position offset
                        y: {
                            if (stateController.currentMood === "confused") return -11;
                            if (stateController.currentMood === "thinking") return 2;
                            if (stateController.currentMood === "shy") return 5;
                            return 0;
                        }
                        Behavior on y { NumberAnimation { duration: 200; easing.type: Easing.OutQuad } }

                        Rectangle {
                            id: rightEye
                            anchors.centerIn: parent
                            anchors.horizontalCenterOffset: gazeTracker.targetGazeX
                            anchors.verticalCenterOffset: gazeTracker.targetGazeY

                            color: canvasWindow.featureColor

                            // Morphing Width
                            width: {
                                if (stateController.currentMood === "happy" || stateController.currentMood === "celebrating") return parent.width * 1.15;
                                if (stateController.currentMood === "sleepy" || stateController.currentMood === "calm") return parent.width * 1.15;
                                if (stateController.currentMood === "surprised" || stateController.currentMood === "alert") return parent.width * 1.38;
                                if (stateController.currentMood === "excited") return parent.width * 1.25;
                                if (stateController.currentMood === "thinking" || stateController.currentMood === "focused") return parent.width * 0.88;
                                if (stateController.currentMood === "confused" || stateController.currentMood === "mischievous") return parent.width * 0.92;
                                return parent.width;
                            }

                            // Morphing Height
                            height: {
                                if (canvasWindow.isBlinking || stateController.currentExpression === "wink_right") return parent.height * 0.08;
                                if (stateController.currentMood === "sleepy") return parent.height * 0.16; // Drowsy slit
                                if (stateController.currentMood === "calm" || stateController.currentMood === "shy") return parent.height * 0.42;
                                if (stateController.currentMood === "happy" || stateController.currentMood === "celebrating") return parent.height * 0.58; // Smiling crescent
                                if (stateController.currentMood === "error" || stateController.currentMood === "alert") return parent.height * 0.65; // Sharp glare
                                if (stateController.currentMood === "surprised") return parent.height * 1.38; // Shocked wide
                                if (stateController.currentMood === "excited") return parent.height * 1.25;
                                if (stateController.currentMood === "listening") return parent.height * 1.18;
                                if (stateController.currentMood === "thinking") return parent.height * 0.65;  // Pondering squint
                                if (stateController.currentMood === "confused") return parent.height * 0.60;  // Quizzical squint
                                if (stateController.currentMood === "mischievous") return parent.height * 0.68;// Smug squint
                                if (stateController.currentMood === "focused") return parent.height * 0.75;
                                return parent.height;
                            }

                            radius: {
                                if (stateController.currentMood === "happy" || stateController.currentMood === "celebrating") return height * 0.45;
                                if (stateController.currentMood === "sleepy" || stateController.currentMood === "calm") return height / 2;
                                return width / 2;
                            }

                            Behavior on width { NumberAnimation { duration: 140; easing.type: Easing.InOutQuad } }
                            Behavior on height { NumberAnimation { duration: 140; easing.type: Easing.InOutQuad } }
                            Behavior on radius { NumberAnimation { duration: 140; easing.type: Easing.InOutQuad } }
                            Behavior on anchors.horizontalCenterOffset { NumberAnimation { duration: 80; easing.type: Easing.OutQuad } }
                            Behavior on anchors.verticalCenterOffset { NumberAnimation { duration: 80; easing.type: Easing.OutQuad } }

                            // Specular Catchlight (Eye sparkle)
                            Rectangle {
                                id: rightCatchlight
                                width: parent.width * 0.32
                                height: width
                                radius: width / 2
                                color: "#ffffff"
                                anchors.top: parent.top
                                anchors.topMargin: parent.height * 0.16
                                anchors.left: parent.left
                                anchors.leftMargin: parent.width * 0.22
                                opacity: {
                                    if (canvasWindow.isBlinking || stateController.currentMood === "sleepy") return 0.0;
                                    if (stateController.currentMood === "celebrating" || stateController.currentMood === "excited") return 0.95;
                                    if (stateController.currentMood === "happy" || stateController.currentMood === "curious") return 0.85;
                                    return 0.65;
                                }
                                Behavior on opacity { NumberAnimation { duration: 150 } }
                            }
                        }
                    }
                }

                // ==================== MOUTH ====================
                Rectangle {
                    id: mouth
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.verticalCenter: parent.top
                    anchors.verticalCenterOffset: {
                        if (stateController.currentMood === "surprised" || stateController.currentMood === "alert") return parent.height * 0.74;
                        if (stateController.currentMood === "happy" || stateController.currentMood === "excited" || stateController.currentMood === "celebrating") return parent.height * 0.69;
                        if (stateController.currentMood === "shy") return parent.height * 0.72;
                        return parent.height * 0.70;
                    }

                    readonly property real eyeSize: leftEyeFrame.width

                    // Mouth Slant/Angle
                    rotation: {
                        if (stateController.currentMood === "mischievous") return 8.5; // Smug smirk
                        if (stateController.currentMood === "curious") return -5.5;
                        if (stateController.currentMood === "confused") return 7.0;
                        if (stateController.currentMood === "thinking") return -4.5;
                        return 0.0;
                    }
                    Behavior on rotation { NumberAnimation { duration: 180; easing.type: Easing.InOutQuad } }

                    // Horizontal position offset (smirk / thinking offset)
                    anchors.horizontalCenterOffset: {
                        if (stateController.currentMood === "mischievous") return 10.0;
                        if (stateController.currentMood === "thinking") return 8.0;
                        if (stateController.currentMood === "curious") return -6.0;
                        return 0.0;
                    }
                    Behavior on anchors.horizontalCenterOffset { NumberAnimation { duration: 180; easing.type: Easing.InOutQuad } }

                    // Morphing Mouth Width
                    width: {
                        if (stateController.isTalking) {
                            var p = talkingTimer.mouthPhase;
                            if (p === 0) return eyeSize * 0.98;  // Open vowel
                            if (p === 1) return eyeSize * 0.52;  // Round O / W
                            if (p === 2) return eyeSize * 0.88;  // Wide consonant
                            return eyeSize * 0.62;               // Semi-open
                        }
                        if (stateController.currentMood === "happy") return eyeSize * 1.25;
                        if (stateController.currentMood === "celebrating") return eyeSize * 1.45; // Wide triumphant grin
                        if (stateController.currentMood === "excited") return eyeSize * 1.35;
                        if (stateController.currentMood === "surprised") return eyeSize * 0.55;   // Narrow tall O
                        if (stateController.currentMood === "alert") return eyeSize * 0.65;
                        if (stateController.currentMood === "thinking") return eyeSize * 0.42;    // Small concentrated ellipse
                        if (stateController.currentMood === "focused") return eyeSize * 0.80;     // Analytical line
                        if (stateController.currentMood === "calm") return eyeSize * 0.70;        // Soft gentle line
                        if (stateController.currentMood === "shy") return eyeSize * 0.48;         // Tiny sweet curve
                        if (stateController.currentMood === "mischievous") return eyeSize * 0.88; // Sharp smirk
                        if (stateController.currentMood === "sleepy") return eyeSize * 0.45;      // Tiny resting line
                        if (stateController.currentMood === "error") return eyeSize * 1.05;       // Wide tense grimace
                        if (stateController.currentMood === "listening") return eyeSize * 0.75;
                        if (stateController.currentMood === "curious" || stateController.currentMood === "confused") return eyeSize * 0.75;
                        return eyeSize * 1.0; // Default & Neutral baseline
                    }

                    // Morphing Mouth Height
                    height: {
                        if (stateController.isTalking) {
                            var p2 = talkingTimer.mouthPhase;
                            if (p2 === 0) return eyeSize * 0.52; // Open Ah
                            if (p2 === 1) return eyeSize * 0.68; // Tall Oh
                            if (p2 === 2) return eyeSize * 0.16; // Closed/flat Mm/Th
                            return eyeSize * 0.40;               // Mid Eh
                        }
                        if (stateController.currentMood === "celebrating") return eyeSize * 0.72;// Giant joyful open grin
                        if (stateController.currentMood === "excited") return eyeSize * 0.65;    // Wide open joy
                        if (stateController.currentMood === "happy") return eyeSize * 0.42;      // Smiling open curve
                        if (stateController.currentMood === "surprised") return eyeSize * 0.78;  // Tall vertical open O
                        if (stateController.currentMood === "mischievous") return eyeSize * 0.28;// Curled smirk
                        if (stateController.currentMood === "shy") return eyeSize * 0.22;        // Subtle curve
                        if (stateController.currentMood === "thinking") return eyeSize * 0.22;   // Small dot/pucker
                        if (stateController.currentMood === "focused") return eyeSize * 0.12;    // Sharp calm slit
                        if (stateController.currentMood === "calm") return eyeSize * 0.14;       // Gentle curve
                        if (stateController.currentMood === "sleepy") return eyeSize * 0.10;     // Subtle line
                        if (stateController.currentMood === "error") return eyeSize * 0.12;      // Straight sharp line
                        if (stateController.currentMood === "listening") return eyeSize * 0.14;
                        return eyeSize * 0.14; // Default & Neutral baseline
                    }

                    radius: {
                        if (stateController.currentMood === "happy" || stateController.currentMood === "excited" || stateController.currentMood === "celebrating") {
                            return height * 0.45; // Smile contour
                        }
                        return height / 2;
                    }

                    color: canvasWindow.featureColor

                    Behavior on width { NumberAnimation { duration: 70; easing.type: Easing.OutQuad } }
                    Behavior on height { NumberAnimation { duration: 70; easing.type: Easing.OutQuad } }
                    Behavior on radius { NumberAnimation { duration: 70; easing.type: Easing.OutQuad } }
                }
            }
        }
    }
}
