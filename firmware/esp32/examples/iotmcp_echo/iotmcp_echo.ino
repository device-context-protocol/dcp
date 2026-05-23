// IoT-MCP-style wire-protocol echo, for apples-to-apples DCP/IoT-MCP
// latency comparison.
//
// IoT-MCP's MCU firmware (see github.com/Duke-CEI-Center/IoT-MCP-Servers,
// servers/BUZZER/main.py et al.) uses newline-delimited JSON over UART:
//
//   in:   {"command": "buzzer", "duration": 1, "frequency": 1000}\n
//   out:  {"result": "ok", "duration": 1, "frequency": 1000}\n
//
// This sketch implements the equivalent for set_brightness on the same
// ESP32-S3 hardware that the DCP smart_panel runs on. Compared head-to-
// head with bench_latency.py against the DCP firmware, the difference is
// pure protocol overhead: same chip, same UART, same baud, same intent.
//
// Build: ESP32S3 Dev Module, PSRAM enabled (QSPI), USBMode=hwcdc,
//        CDCOnBoot=cdc -- identical to smart_panel build flags.

#include <Arduino.h>
#include <ArduinoJson.h>

// Big enough for any IoT-MCP-style command we throw at it.
static StaticJsonDocument<512> doc;
static StaticJsonDocument<256> reply;
static String linebuf;

void setup() {
    Serial.begin(115200);
    // Match the DCP firmware's CDC settle delay so the two benches see
    // the same startup behaviour from the host's perspective.
    delay(2000);
}

void loop() {
    while (Serial.available()) {
        char c = (char)Serial.read();
        if (c == '\n') {
            // Parse + handle the line.
            reply.clear();
            DeserializationError err = deserializeJson(doc, linebuf);
            if (err) {
                reply["error"] = err.c_str();
            } else {
                const char* cmd = doc["command"] | "";
                if (strcmp(cmd, "set_brightness") == 0) {
                    float level = doc["level"] | -1.0f;
                    if (level < 0 || level > 100) {
                        reply["error"] = "out of range";
                    } else {
                        // No actual hardware action — the DCP smart_panel
                        // handler also doesn't drive an LED on this
                        // hardware (the LCD work is separate). Pure
                        // protocol path.
                        reply["result"] = "ok";
                        reply["level"]  = level;
                    }
                } else {
                    reply["error"] = "unknown command";
                }
            }
            serializeJson(reply, Serial);
            Serial.write('\n');
            linebuf = "";
        } else if (c != '\r') {
            linebuf += c;
        }
    }
}
