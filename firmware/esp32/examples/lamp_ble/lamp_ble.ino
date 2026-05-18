// Smart-lamp over BLE.
//
// Pair with the Python Bridge:
//
//     dcp serve examples/lamp_manifest.yaml \
//             --ble AA:BB:CC:DD:EE:FF \
//             --ble-service 12345678-1234-5678-1234-567812345678
//
// On macOS / Linux you can also discover the address by running:
//     python -m bleak.examples.discover

#include <NimBLEDevice.h>
#include "DCP.h"
#include "DCPBle.h"

static const char* SERVICE_UUID = "12345678-1234-5678-1234-567812345678";

constexpr int LED_PIN     = 2;
constexpr int PWM_FREQ_HZ = 5000;
constexpr int PWM_BITS    = 8;
// NOTE: requires Arduino-ESP32 core 3.0+. See lamp/lamp.ino for v2.x notes.

static float g_brightness = 0.0f;

static dcp::Status handle_set_brightness(uint8_t kind,
                                         dcp::CborReader& params,
                                         dcp::CborMap& reply,
                                         void*) {
    double level = 0.0;
    while (params.remaining() > 0) {
        const char* key = nullptr;
        size_t key_len = 0;
        if (!params.next_key(&key, &key_len)) return dcp::STATUS_DENIED;
        if (key_len == 5 && memcmp(key, "level", 5) == 0) {
            if (!params.read_float(&level)) return dcp::STATUS_RANGE;
        } else {
            params.skip();
        }
    }
    if (level < 0.0 || level > 100.0) return dcp::STATUS_RANGE;
    if (kind == dcp::KIND_DRY_RUN) {
        reply.add_float("would_set", level);
        return dcp::STATUS_OK;
    }
    g_brightness = (float)level;
    ledcWrite(LED_PIN, (uint32_t)(g_brightness * 2.55f));
    return dcp::STATUS_OK;
}

static dcp::Status handle_read_brightness(uint8_t,
                                          dcp::CborReader&,
                                          dcp::CborMap& reply,
                                          void*) {
    reply.add_float("value", (double)g_brightness);
    return dcp::STATUS_OK;
}

static dcp::IntentBinding bindings[] = {
    { DCP_ID("set_brightness"),  handle_set_brightness,  nullptr },
    { DCP_ID("read_brightness"), handle_read_brightness, nullptr },
};

static dcp::DCPBle* ble = nullptr;

void setup() {
    Serial.begin(115200);
    ledcAttach(LED_PIN, PWM_FREQ_HZ, PWM_BITS);

    NimBLEDevice::init("dcp-lamp");
    static dcp::DCPBle inst(SERVICE_UUID, bindings,
                            sizeof(bindings) / sizeof(bindings[0]));
    ble = &inst;
    ble->begin();

    Serial.println("DCP BLE peripheral up. Service UUID:");
    Serial.println(SERVICE_UUID);
}

void loop() {
    // NimBLE drives I/O from its own task; nothing to poll here.
    delay(1000);
}
