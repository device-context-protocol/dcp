// Smart-lamp example for the DCP reference firmware.
//
// Pair with the Python Bridge running on a host machine:
//
//     dcp serve examples/lamp_manifest.yaml --serial COM3   (Windows)
//     dcp serve examples/lamp_manifest.yaml --serial /dev/ttyUSB0   (Linux)
//
// Hardware: any ESP32 dev board or ESP8266 (NodeMCU / Wemos D1). The
// built-in LED is on GPIO 2 on most WROOM-32 dev kits. On ESP8266 the
// onboard LED is usually GPIO 2 as well but ACTIVE-LOW — flip the duty
// inversion below if your board has a different scheme.
//
// PWM API:
//   ESP32:   Arduino-ESP32 core 3.x v3 LEDC API (ledcAttach / ledcWrite)
//   ESP8266: stock analogWrite() (range remapped to 0..255 to match)
//
// All other DCP code paths are platform-independent.

#include "DCP.h"

constexpr int LED_PIN     = 2;       // built-in LED on most WROOM-32 dev boards
constexpr int PWM_FREQ_HZ = 5000;
constexpr int PWM_BITS    = 8;
constexpr int PWM_MAX     = (1 << PWM_BITS) - 1;     // 255

static inline void lamp_pwm_setup() {
#if defined(ESP32)
    ledcAttach(LED_PIN, PWM_FREQ_HZ, PWM_BITS);      // core 3.x v3 API
#elif defined(ESP8266)
    analogWriteFreq(PWM_FREQ_HZ);
    analogWriteRange(PWM_MAX);
    pinMode(LED_PIN, OUTPUT);
#else
    pinMode(LED_PIN, OUTPUT);                        // fallback: digital only
#endif
}

static inline void lamp_pwm_write(uint32_t duty) {
#if defined(ESP32)
    ledcWrite(LED_PIN, duty);
#elif defined(ESP8266)
    analogWrite(LED_PIN, duty);
#else
    digitalWrite(LED_PIN, duty > (PWM_MAX / 2) ? HIGH : LOW);
#endif
}

static float g_brightness = 0.0f;
static uint8_t g_r = 255, g_g = 255, g_b = 255;   // current target RGB (no real LED bound)

static dcp::Status handle_set_brightness(uint8_t kind,
                                         dcp::CborReader& params,
                                         dcp::CborMap& reply,
                                         void* /*user*/) {
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
    uint32_t duty = (uint32_t)(g_brightness * 2.55f);
    lamp_pwm_write(duty);
    return dcp::STATUS_OK;
}

static dcp::Status handle_read_brightness(uint8_t kind,
                                          dcp::CborReader& /*params*/,
                                          dcp::CborMap& reply,
                                          void* /*user*/) {
    reply.add_float("value", (double)g_brightness);
    return dcp::STATUS_OK;
}

static dcp::Status handle_set_color(uint8_t kind,
                                    dcp::CborReader& params,
                                    dcp::CborMap& reply,
                                    void* /*user*/) {
    int64_t r = g_r, g = g_g, b = g_b;
    while (params.remaining() > 0) {
        const char* key = nullptr;
        size_t key_len = 0;
        if (!params.next_key(&key, &key_len)) return dcp::STATUS_DENIED;
        if      (key_len == 1 && key[0] == 'r') { if (!params.read_int(&r)) return dcp::STATUS_RANGE; }
        else if (key_len == 1 && key[0] == 'g') { if (!params.read_int(&g)) return dcp::STATUS_RANGE; }
        else if (key_len == 1 && key[0] == 'b') { if (!params.read_int(&b)) return dcp::STATUS_RANGE; }
        else                                    { params.skip(); }
    }
    if (r < 0 || r > 255 || g < 0 || g > 255 || b < 0 || b > 255) return dcp::STATUS_RANGE;

    if (kind == dcp::KIND_DRY_RUN) {
        reply.add_int("would_r", r);
        reply.add_int("would_g", g);
        reply.add_int("would_b", b);
        return dcp::STATUS_OK;
    }

    g_r = (uint8_t)r; g_g = (uint8_t)g; g_b = (uint8_t)b;
    // The default WROOM-32 dev board has no RGB LED. We acknowledge by giving
    // a visible 80ms flash on the built-in brightness LED, then restoring it.
    uint32_t saved = (uint32_t)(g_brightness * 2.55f);
    lamp_pwm_write(255); delay(80);
    lamp_pwm_write(0);   delay(80);
    lamp_pwm_write(saved);
    return dcp::STATUS_OK;
}

// Blink the built-in LED `times` times, each cycle = `period`ms on + `period`ms off.
// Note: blocking implementation — the main loop can't service DCP frames during
// the blink. Manifest range caps total time at 20 * 2000 * 2 = 80s worst case;
// a real product would use a millis()-based state machine instead.
static dcp::Status handle_blink(uint8_t kind,
                                dcp::CborReader& params,
                                dcp::CborMap& reply,
                                void* /*user*/) {
    int64_t times = 3;
    double  period_ms = 200.0;     // duration is encoded as CBOR float on the wire
    while (params.remaining() > 0) {
        const char* key = nullptr;
        size_t key_len = 0;
        if (!params.next_key(&key, &key_len)) return dcp::STATUS_DENIED;
        if      (key_len == 5 && memcmp(key, "times",  5) == 0) { if (!params.read_int(&times))       return dcp::STATUS_RANGE; }
        else if (key_len == 6 && memcmp(key, "period", 6) == 0) { if (!params.read_float(&period_ms)) return dcp::STATUS_RANGE; }
        else                                                    { params.skip(); }
    }
    if (times < 1 || times > 20)              return dcp::STATUS_RANGE;
    if (period_ms < 50.0 || period_ms > 2000.0) return dcp::STATUS_RANGE;

    uint32_t period = (uint32_t)period_ms;
    if (kind == dcp::KIND_DRY_RUN) {
        reply.add_int("would_blink_times",  times);
        reply.add_int("would_blink_period", (int64_t)period);
        return dcp::STATUS_OK;
    }

    // Save current brightness so we can restore it after the blink.
    uint32_t saved = (uint32_t)(g_brightness * 2.55f);
    for (int64_t i = 0; i < times; ++i) {
        lamp_pwm_write(255);        delay(period);
        lamp_pwm_write(0);          delay(period);
    }
    lamp_pwm_write(saved);
    return dcp::STATUS_OK;
}

// Intent IDs are resolved at compile time via DCP_ID().
// Keep these strings in sync with examples/lamp_manifest.yaml.
static dcp::IntentBinding bindings[] = {
    { DCP_ID("set_brightness"),  handle_set_brightness,  nullptr },
    { DCP_ID("set_color"),       handle_set_color,       nullptr },
    { DCP_ID("read_brightness"), handle_read_brightness, nullptr },
    { DCP_ID("blink"),           handle_blink,           nullptr },
};

static dcp::DCP* dcp_instance = nullptr;

void setup() {
    Serial.begin(115200);

    lamp_pwm_setup();

    static dcp::DCP instance(Serial, bindings, sizeof(bindings) / sizeof(bindings[0]));
    dcp_instance = &instance;
}

void loop() {
    if (dcp_instance) dcp_instance->poll();
}
