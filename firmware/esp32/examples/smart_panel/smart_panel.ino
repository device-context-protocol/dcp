// Smart Panel — DCP firmware for LILYGO T-Panel S3 (H720 CAN FD variant).
//
// This is the v0.3 + v0.4 demo firmware. It exposes 12 intents and 2 events
// over UART-DCP, matching examples/smart_panel_manifest.yaml.
//
// Hardware: LILYGO T-Panel S3, ST7701S 4" 480×480 IPS, CST3240 capacitive
// touch, MORNSUN TD501MCANFD CAN FD transceiver (classic CAN @ 500kbps via
// ESP32-S3 TWAI), XL9535 GPIO expander.
//
// Required libraries (Arduino Library Manager):
//   - GFX Library for Arduino (Arduino_GFX, by moononournation)
//   - TouchLib (by mmMicky)
//
// Build target: ESP32S3 Dev Module, Flash 16MB, PSRAM OPI 8MB.

// Temporary bring-up flag: skip all LCD/touch init so the firmware boots
// on boards where PSRAM is absent or the RGB panel config is wrong.
// DCP UART + buzzer + CAN keep working; display handlers become no-ops.
#define DCP_NO_DISPLAY 1

#include "DCP.h"
#include "DCPCrypto.h"
#include <Arduino.h>
#include <Wire.h>
#if !DCP_NO_DISPLAY
#include <Arduino_GFX_Library.h>
// TouchLib needs the chip model selected before the header is included.
// The T-Panel S3's CST3240 is a mutual-capacitance controller.
#define TOUCH_MODULES_CST_MUTUAL
#include "TouchLib.h"
#endif
#include "driver/twai.h"

// ───────── Pin definitions (from T-Panel pin_config.h) ─────────
#define IIC_SDA       17
#define IIC_SCL       18
#define TOUCH_INT     21
#define LCD_WIDTH     480
#define LCD_HEIGHT    480
#define LCD_BL        14
#define CAN_TX        16
#define CAN_RX        15
// ⚠ Pin 19/20 on ESP32-S3 are USB D-/D+. Driving them as a GPIO output
// disconnects the native USB-Serial/JTAG and makes the COM port vanish.
// Anything user-added (buzzer, extra LED, etc.) on this board should be
// on a pin that the RGB display, I2C, CAN, touch, PSRAM, and USB are
// not already using. GPIO 38 is free and PWM-capable.
#define BUZZER_PIN    38           // user-added: solder piezo or PAM8403 + 8Ω here
#define DCP_UART      Serial1      // dedicated UART for the DCP host link
#define DCP_TX        47           // ⚠ shared with ESP32-H2 RX; if conflict use 3/8
#define DCP_RX        48           // ⚠ shared with ESP32-H2 TX; same caveat
// Default DCP transport is the USB CDC Serial — use that for first bring-up,
// switch to Serial1 + above pins for production.

// XL9535 (GPIO expander on I2C) — pin map within the expander
#define XL95X5_CS         17
#define XL95X5_SCLK       15
#define XL95X5_MOSI       16
#define XL95X5_TOUCH_RST  4
#define XL95X5_LCD_RST    5
#define CST3240_ADDR      0x5A

constexpr int PWM_BL_HZ    = 5000;
constexpr int PWM_BUZZER_HZ_PLACEHOLDER = 1000;   // overwritten per-note
constexpr int PWM_BITS     = 8;

// ───────── Global state ─────────
static float    g_backlight = 50.0f;
static uint8_t  g_r = 0, g_g = 0, g_b = 0;
static int16_t  g_last_touch_x = -1, g_last_touch_y = -1;
static bool     g_touch_pressed = false;

// Last received CAN frame, for can_receive_last() intent.
static volatile bool      g_can_have_last = false;
static twai_message_t     g_can_last;

// Score playback state (set by play_score, advanced in loop())
struct ScoreNote { uint16_t freq_hz; uint16_t duration_ms; };
static ScoreNote g_score[64];
static uint8_t   g_score_len = 0;
static uint8_t   g_score_pos = 0;
static uint32_t  g_score_next_ms = 0;
static bool      g_score_playing = false;

// ───────── Display objects ─────────
#if !DCP_NO_DISPLAY
Arduino_DataBus *bus = new Arduino_XL9535SWSPI(
    IIC_SDA, IIC_SCL, -1, XL95X5_CS, XL95X5_SCLK, XL95X5_MOSI);
Arduino_ESP32RGBPanel *rgbpanel = new Arduino_ESP32RGBPanel(
    -1, 40, 39, 41,
    1, 2, 3, 4, 5,                           // B0..B4
    6, 7, 8, 9, 10, 11,                      // G0..G5
    12, 13, 42, 46, 45,                      // R0..R4
    1, 20, 2, 0,
    1, 30, 8, 1,
    10, 6'000'000L, false, 0, 0,
    LCD_WIDTH * 10);   // bounce buffer = 10 rows in DRAM, fixes QSPI PSRAM bandwidth underrun
Arduino_RGB_Display *gfx = new Arduino_RGB_Display(
    LCD_WIDTH, LCD_HEIGHT, rgbpanel, 0, true,
    bus, -1, st7701_type9_init_operations, sizeof(st7701_type9_init_operations));

TouchLib touch(Wire, IIC_SDA, IIC_SCL, CST3240_ADDR);
#endif

// ───────── DCP intent handlers ─────────

static dcp::Status read_int(dcp::CborReader& p, const char* key, size_t klen,
                            int64_t* out) {
    const char* k; size_t kl;
    while (p.remaining() > 0) {
        if (!p.next_key(&k, &kl)) return dcp::STATUS_DENIED;
        if (kl == klen && memcmp(k, key, klen) == 0) {
            return p.read_int(out) ? dcp::STATUS_OK : dcp::STATUS_RANGE;
        }
        p.skip();
    }
    return dcp::STATUS_RANGE;   // key not found
}

static dcp::Status h_set_backlight(uint8_t kind, dcp::CborReader& params,
                                   dcp::CborMap& reply, void*) {
    double level = 50.0;
    while (params.remaining() > 0) {
        const char* k; size_t kl;
        if (!params.next_key(&k, &kl)) return dcp::STATUS_DENIED;
        if (kl == 5 && memcmp(k, "level", 5) == 0) {
            if (!params.read_float(&level)) return dcp::STATUS_RANGE;
        } else { params.skip(); }
    }
    if (level < 0 || level > 100) return dcp::STATUS_RANGE;
    if (kind == dcp::KIND_DRY_RUN) {
        reply.add_float("would_set", level);
        return dcp::STATUS_OK;
    }
    g_backlight = (float)level;
    ledcWrite(LCD_BL, (uint32_t)(g_backlight * 2.55f));
    return dcp::STATUS_OK;
}

static dcp::Status h_set_color(uint8_t kind, dcp::CborReader& params,
                               dcp::CborMap& reply, void*) {
    int64_t r = g_r, g = g_g, b = g_b;
    while (params.remaining() > 0) {
        const char* k; size_t kl;
        if (!params.next_key(&k, &kl)) return dcp::STATUS_DENIED;
        if      (kl == 1 && k[0] == 'r') { if (!params.read_int(&r)) return dcp::STATUS_RANGE; }
        else if (kl == 1 && k[0] == 'g') { if (!params.read_int(&g)) return dcp::STATUS_RANGE; }
        else if (kl == 1 && k[0] == 'b') { if (!params.read_int(&b)) return dcp::STATUS_RANGE; }
        else                              { params.skip(); }
    }
    if (r<0||r>255||g<0||g>255||b<0||b>255) return dcp::STATUS_RANGE;
    if (kind == dcp::KIND_DRY_RUN) {
        reply.add_int("would_r", r); reply.add_int("would_g", g); reply.add_int("would_b", b);
        return dcp::STATUS_OK;
    }
    g_r = (uint8_t)r; g_g = (uint8_t)g; g_b = (uint8_t)b;
#if !DCP_NO_DISPLAY
    uint16_t rgb565 = gfx->color565(g_r, g_g, g_b);
    gfx->fillRect(20, 360, 440, 100, rgb565);   // bottom color swatch
#endif
    return dcp::STATUS_OK;
}

static dcp::Status h_display_text(uint8_t, dcp::CborReader& params,
                                  dcp::CborMap&, void*) {
    char buf[24] = {0};
    int64_t line = 0, size = 2;
    while (params.remaining() > 0) {
        const char* k; size_t kl;
        if (!params.next_key(&k, &kl)) return dcp::STATUS_DENIED;
        if (kl == 4 && memcmp(k, "text", 4) == 0) {
            const char* s; size_t slen;
            if (!params.read_string(&s, &slen)) return dcp::STATUS_RANGE;
            memcpy(buf, s, slen < 23 ? slen : 23);
        } else if (kl == 4 && memcmp(k, "line", 4) == 0) {
            if (!params.read_int(&line)) return dcp::STATUS_RANGE;
        } else if (kl == 4 && memcmp(k, "size", 4) == 0) {
            if (!params.read_int(&size)) return dcp::STATUS_RANGE;
        } else { params.skip(); }
    }
#if !DCP_NO_DISPLAY
    gfx->setTextSize((uint8_t)size);
    gfx->setCursor(10, 20 + (int)line * 32 * (int)size);
    gfx->setTextColor(0xFFFF, 0x0000);
    gfx->print(buf);
#else
    (void)buf; (void)line; (void)size;
#endif
    return dcp::STATUS_OK;
}

static dcp::Status h_clear_screen(uint8_t, dcp::CborReader&, dcp::CborMap&, void*) {
#if !DCP_NO_DISPLAY
    gfx->fillScreen(0);
#endif
    return dcp::STATUS_OK;
}

static dcp::Status h_play_tone(uint8_t kind, dcp::CborReader& params,
                               dcp::CborMap& reply, void*) {
    int64_t freq = 440, duration = 200;
    while (params.remaining() > 0) {
        const char* k; size_t kl;
        if (!params.next_key(&k, &kl)) return dcp::STATUS_DENIED;
        if      (kl == 4 && memcmp(k, "freq",     4) == 0) { if (!params.read_int(&freq)) return dcp::STATUS_RANGE; }
        else if (kl == 8 && memcmp(k, "duration", 8) == 0) { if (!params.read_int(&duration)) return dcp::STATUS_RANGE; }
        else                                               { params.skip(); }
    }
    if (freq < 50 || freq > 5000 || duration < 10 || duration > 5000) return dcp::STATUS_RANGE;
    if (kind == dcp::KIND_DRY_RUN) {
        reply.add_int("would_play_hz", freq);
        return dcp::STATUS_OK;
    }
    tone(BUZZER_PIN, (uint32_t)freq, (uint32_t)duration);
    return dcp::STATUS_OK;
}

// Parses one MML token, e.g. "C4q", "G#4h", "R8e"; returns false on end.
// Writes freq_hz=0 for rests. Duration_ms is computed against tempo.
static bool parse_mml_note(const char*& s, const char* end, uint16_t tempo,
                           uint16_t& freq_hz, uint16_t& dur_ms) {
    while (s < end && (*s == ' ' || *s == '\t' || *s == ',')) ++s;
    if (s >= end) return false;
    char letter = *s++;
    int8_t semitone_offset = 0;
    if (s < end && (*s == '#' || *s == 'b')) { semitone_offset = (*s == '#' ? 1 : -1); ++s; }
    int octave = (s < end && *s >= '0' && *s <= '9') ? (*s++ - '0') : 4;
    char durch = (s < end) ? *s++ : 'q';
    bool dotted = (s < end && *s == '.');
    if (dotted) ++s;

    // Chromatic index from C: C=0 D=2 E=4 F=5 G=7 A=9 B=11
    int chromatic = -1;
    switch (letter) {
        case 'C': chromatic = 0;  break;
        case 'D': chromatic = 2;  break;
        case 'E': chromatic = 4;  break;
        case 'F': chromatic = 5;  break;
        case 'G': chromatic = 7;  break;
        case 'A': chromatic = 9;  break;
        case 'B': chromatic = 11; break;
        case 'R': case 'r': freq_hz = 0; break;
        default:            freq_hz = 0; break;
    }
    if (chromatic >= 0) {
        // MIDI note number: 12*(octave+1) + chromatic. A4 (440Hz) = MIDI 69.
        int midi = 12 * (octave + 1) + chromatic + semitone_offset;
        freq_hz = (uint16_t)(440.0f * powf(2.0f, (midi - 69) / 12.0f));
    }
    {
        // beat ms at 4/4 quarter = 60000 / tempo
        uint32_t beat_ms = 60000UL / (tempo ? tempo : 120);
        uint32_t d;
        switch (durch) {
            case 'w': d = beat_ms * 4; break;
            case 'h': d = beat_ms * 2; break;
            case 'q': d = beat_ms; break;
            case 'e': d = beat_ms / 2; break;
            case 's': d = beat_ms / 4; break;
            default:  d = beat_ms; break;
        }
        if (dotted) d = (d * 3) / 2;
        dur_ms = (uint16_t)d;
    }
    return true;
}

static dcp::Status h_play_score(uint8_t kind, dcp::CborReader& params,
                                dcp::CborMap& reply, void*) {
    const char* mel = nullptr; size_t mlen = 0;
    int64_t tempo = 120;
    while (params.remaining() > 0) {
        const char* k; size_t kl;
        if (!params.next_key(&k, &kl)) return dcp::STATUS_DENIED;
        if      (kl == 6 && memcmp(k, "melody", 6) == 0) {
            if (!params.read_string(&mel, &mlen)) return dcp::STATUS_RANGE;
        } else if (kl == 5 && memcmp(k, "tempo",  5) == 0) {
            if (!params.read_int(&tempo)) return dcp::STATUS_RANGE;
        } else { params.skip(); }
    }
    if (!mel || mlen == 0) return dcp::STATUS_RANGE;
    if (tempo < 40 || tempo > 240) return dcp::STATUS_RANGE;

    // Parse the melody into our score buffer.
    const char* s = mel; const char* end = mel + mlen;
    g_score_len = 0;
    uint16_t total_ms = 0;
    while (g_score_len < (sizeof(g_score) / sizeof(g_score[0]))) {
        uint16_t f, d;
        if (!parse_mml_note(s, end, (uint16_t)tempo, f, d)) break;
        g_score[g_score_len++] = { f, d };
        total_ms += d;
    }

    if (kind == dcp::KIND_DRY_RUN) {
        reply.add_int("notes",      g_score_len);
        reply.add_int("duration_ms", total_ms);
        g_score_len = 0;
        return dcp::STATUS_OK;
    }

    g_score_pos      = 0;
    g_score_next_ms  = millis();
    g_score_playing  = true;
    return dcp::STATUS_OK;
}

static dcp::Status h_stop_playback(uint8_t, dcp::CborReader&, dcp::CborMap&, void*) {
    g_score_playing = false;
    noTone(BUZZER_PIN);
    return dcp::STATUS_OK;
}

static dcp::Status h_read_touch(uint8_t, dcp::CborReader&, dcp::CborMap& reply, void*) {
    reply.add_bool("value", g_touch_pressed);
    return dcp::STATUS_OK;
}

static dcp::Status h_can_send(uint8_t kind, dcp::CborReader& params,
                              dcp::CborMap& reply, void*) {
    int64_t id = 0;
    bool extd = false;
    const char* data_hex = nullptr; size_t data_len = 0;
    while (params.remaining() > 0) {
        const char* k; size_t kl;
        if (!params.next_key(&k, &kl)) return dcp::STATUS_DENIED;
        if      (kl == 2 && memcmp(k, "id",       2) == 0) { if (!params.read_int(&id)) return dcp::STATUS_RANGE; }
        else if (kl == 8 && memcmp(k, "data_hex", 8) == 0) { if (!params.read_string(&data_hex, &data_len)) return dcp::STATUS_RANGE; }
        else if (kl == 8 && memcmp(k, "extended", 8) == 0) { if (!params.read_bool(&extd)) return dcp::STATUS_RANGE; }
        else                                               { params.skip(); }
    }
    if (!data_hex || data_len > 16 || (data_len & 1)) return dcp::STATUS_RANGE;
    twai_message_t msg = {};
    msg.identifier        = (uint32_t)id;
    msg.extd              = extd;
    msg.data_length_code  = data_len / 2;
    for (size_t i = 0; i < data_len; i += 2) {
        char hi = data_hex[i], lo = data_hex[i + 1];
        auto hex = [](char c) -> int { return c >= '0' && c <= '9' ? c - '0'
                                           : c >= 'a' && c <= 'f' ? 10 + c - 'a'
                                           : c >= 'A' && c <= 'F' ? 10 + c - 'A' : -1; };
        int h = hex(hi), l = hex(lo);
        if (h < 0 || l < 0) return dcp::STATUS_RANGE;
        msg.data[i / 2] = (uint8_t)((h << 4) | l);
    }
    if (kind == dcp::KIND_DRY_RUN) {
        reply.add_int("would_send_id", id);
        return dcp::STATUS_OK;
    }
    if (twai_transmit(&msg, pdMS_TO_TICKS(50)) != ESP_OK) return dcp::STATUS_BUSY;
    return dcp::STATUS_OK;
}

static dcp::Status h_can_receive_last(uint8_t, dcp::CborReader&,
                                      dcp::CborMap& reply, void*) {
    if (!g_can_have_last) {
        reply.add_string("value", "");
        return dcp::STATUS_OK;
    }
    char buf[48];
    int n = snprintf(buf, sizeof(buf), "id=0x%x data=", (unsigned)g_can_last.identifier);
    for (int i = 0; i < g_can_last.data_length_code && n < (int)sizeof(buf) - 3; ++i) {
        n += snprintf(buf + n, sizeof(buf) - n, "%02x", g_can_last.data[i]);
    }
    reply.add_string("value", buf);
    return dcp::STATUS_OK;
}

// v0.5 stubs — return denied for now.
static dcp::Status h_move_motor(uint8_t, dcp::CborReader&, dcp::CborMap&, void*) {
    return dcp::STATUS_DENIED;
}
static dcp::Status h_read_motor_position(uint8_t, dcp::CborReader&, dcp::CborMap&, void*) {
    return dcp::STATUS_DENIED;
}

// ───────── DCP binding table — keep in sync with smart_panel_manifest.yaml ─────────
static dcp::IntentBinding bindings[] = {
    { DCP_ID("set_backlight"),       h_set_backlight,       nullptr },
    { DCP_ID("set_color"),           h_set_color,           nullptr },
    { DCP_ID("display_text"),        h_display_text,        nullptr },
    { DCP_ID("clear_screen"),        h_clear_screen,        nullptr },
    { DCP_ID("play_tone"),           h_play_tone,           nullptr },
    { DCP_ID("play_score"),          h_play_score,          nullptr },
    { DCP_ID("stop_playback"),       h_stop_playback,       nullptr },
    { DCP_ID("read_touch"),          h_read_touch,          nullptr },
    { DCP_ID("can_send"),            h_can_send,            nullptr },
    { DCP_ID("can_receive_last"),    h_can_receive_last,    nullptr },
    { DCP_ID("move_motor"),          h_move_motor,          nullptr },     // v0.5 stub
    { DCP_ID("read_motor_position"), h_read_motor_position, nullptr },     // v0.5 stub
};
static dcp::DCP* dcp_link = nullptr;

// ───────── CAN init ─────────
static void init_can() {
    twai_general_config_t g = TWAI_GENERAL_CONFIG_DEFAULT(
        (gpio_num_t)CAN_TX, (gpio_num_t)CAN_RX, TWAI_MODE_NORMAL);
    twai_timing_config_t  t = TWAI_TIMING_CONFIG_500KBITS();
    twai_filter_config_t  f = TWAI_FILTER_CONFIG_ACCEPT_ALL();
    if (twai_driver_install(&g, &t, &f) == ESP_OK) twai_start();
}

static void pump_can() {
    twai_message_t msg;
    while (twai_receive(&msg, 0) == ESP_OK) {
        g_can_last = msg;
        g_can_have_last = true;
        // TODO: emit `can_received` DCP event back to host. v0.4 work.
    }
}

// ───────── Score scheduler ─────────
static void pump_score() {
    if (!g_score_playing) return;
    uint32_t now = millis();
    if (now < g_score_next_ms) return;
    if (g_score_pos >= g_score_len) {
        g_score_playing = false;
        noTone(BUZZER_PIN);
        return;
    }
    ScoreNote& n = g_score[g_score_pos++];
    if (n.freq_hz == 0) {
        noTone(BUZZER_PIN);
    } else {
        tone(BUZZER_PIN, n.freq_hz);
    }
    g_score_next_ms = now + n.duration_ms;
}

// ───────── Touch polling ─────────
#if !DCP_NO_DISPLAY
static void pump_touch() {
    if (!touch.read()) {
        g_touch_pressed = false;
        return;
    }
    TP_Point p = touch.getPoint(0);
    g_touch_pressed = true;
    g_last_touch_x = p.x;
    g_last_touch_y = p.y;
    // TODO: emit `touch_pressed` DCP event with x/y/region. v0.4 work.
}
#else
static void pump_touch() {}
#endif

// ───────── Setup / loop ─────────
void setup() {
    Serial.begin(115200);   // bring-up over USB-CDC first; switch to Serial1 for prod
    delay(3000);            // diagnostic: wait long enough for host to grab CDC
    Serial.println("[1] setup start");
    Serial.flush();

    // Diagnostic: force backlight ON with plain GPIO, skip LEDC entirely.
    pinMode(LCD_BL, OUTPUT);
    digitalWrite(LCD_BL, HIGH);
    Serial.println("[2] backlight HIGH");

    // XL9535 (TCA9535) is rated max 400kHz — 800kHz was a bad idea.
    Wire.begin(IIC_SDA, IIC_SCL, 400000);
    Serial.println("[3] Wire begin");

    // I2C scan — must see XL9535 (0x20) for LCD_RST control, CST3240 (0x5A) for touch.
    Serial.print("[3a] I2C scan:");
    int found = 0;
    for (uint8_t addr = 1; addr < 127; addr++) {
        Wire.beginTransmission(addr);
        if (Wire.endTransmission() == 0) {
            Serial.printf(" 0x%02x", addr);
            found++;
        }
    }
    Serial.printf("  (%d devices)\n", found);

    // WORKAROUND: Arduino_XL9535SWSPI::begin() only sets port 0 to OUTPUT,
    // leaving port 1 (where CS=17 SCLK=15 MOSI=16 live, per the lib's
    // P1.x = 10..17 addressing) as INPUT. The bit-banged SPI writes never
    // drive the lines, so the LCD never receives its init sequence.
    // Force both ports to OUTPUT and drive everything HIGH (releases
    // LCD_RST on P0.5, parks CS/SCLK/MOSI in idle state).
    auto xl_w = [](uint8_t reg, uint8_t val) {
        Wire.beginTransmission(0x20);
        Wire.write(reg); Wire.write(val);
        Wire.endTransmission();
    };
    xl_w(0x06, 0x00);  // CONFIG_PORT_0 = 0 → all OUTPUT
    xl_w(0x07, 0x00);  // CONFIG_PORT_1 = 0 → all OUTPUT
    xl_w(0x02, 0xFF);  // OUTPUT_PORT_0 = 0xFF → all HIGH (releases LCD_RST, TOUCH_RST)
    xl_w(0x03, 0xFF);  // OUTPUT_PORT_1 = 0xFF → all HIGH (CS/SCLK/MOSI idle high)
    delay(50);
    Serial.println("[3b] XL9535 ports forced OUTPUT, LCD_RST released");
    Serial.flush();

    // Note: do NOT ledcAttach BUZZER_PIN — Arduino's tone()/noTone() owns
    // its own LEDC channel internally in core 3.x. Doing both fights.
    pinMode(BUZZER_PIN, OUTPUT);
    Serial.println("[4] buzzer pin OK");

#if !DCP_NO_DISPLAY
    gfx->begin();
    Serial.println("[5] gfx->begin done");

    gfx->fillScreen(0xFFFF);
    gfx->setTextColor(0x0000);
    gfx->setTextSize(3);
    gfx->setCursor(10, 200);
    gfx->print("DCP smart-panel-01");
    Serial.println("[6] draw done");

    touch.init();
    Serial.println("[7] touch init done");
#else
    Serial.println("[5-7] display skipped (DCP_NO_DISPLAY)");
#endif

    init_can();
    Serial.println("[8] can init done");

    static dcp::DCP link(Serial, bindings, sizeof(bindings) / sizeof(bindings[0]));
    dcp_link = &link;
    Serial.println("[9] setup complete");
}

void loop() {
    if (dcp_link) dcp_link->poll();
    pump_can();
    pump_score();
    pump_touch();
}
