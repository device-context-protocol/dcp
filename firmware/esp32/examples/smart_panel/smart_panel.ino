// Smart Panel — DCP + LVGL demo firmware for LILYGO T-Panel S3.
//
// Mirrors the LilyGo factory Lvgl.ino panel/LVGL config 1:1 (PCLK 6MHz,
// library's built-in st7701_type9 init, full_refresh=1, DRAM draw buffers),
// then layers DCP intent handlers on top so an MCP host can drive the
// LVGL widgets remotely.
//
// Earlier attempts that diverged from the official config (16MHz PCLK,
// custom RGB565 init, partial-refresh LVGL) all produced the 2-frame
// ping-pong artifact. The official config is the only one that's known
// to render cleanly on this hardware.
//
// Build target: Arduino-ESP32 2.0.14 + Arduino_GFX 1.4.6 + LVGL 8.3.5.
//   Board:     ESP32S3 Dev Module
//   PSRAM:     QSPI (8MB)
//   FlashSize: 16M
//   USBMode:   hwcdc
//   CDCOnBoot: cdc

#include "DCP.h"
#include "DCPCrypto.h"
#include <Arduino.h>
#include <Wire.h>
#include <lvgl.h>
#include <Arduino_GFX_Library.h>
#define TOUCH_MODULES_CST_MUTUAL
#include "TouchLib.h"
#include "driver/twai.h"

// ───────── Pin definitions (from LilyGo Mylibrary/pin_config.h) ─────────
#define IIC_SDA           17
#define IIC_SCL           18
#define TOUCH_INT         21
#define LCD_WIDTH         480
#define LCD_HEIGHT        480
#define LCD_VSYNC         40
#define LCD_HSYNC         39
#define LCD_PCLK          41
#define LCD_B0 1
#define LCD_B1 2
#define LCD_B2 3
#define LCD_B3 4
#define LCD_B4 5
#define LCD_G0 6
#define LCD_G1 7
#define LCD_G2 8
#define LCD_G3 9
#define LCD_G4 10
#define LCD_G5 11
#define LCD_R0 12
#define LCD_R1 13
#define LCD_R2 42
#define LCD_R3 46
#define LCD_R4 45
#define LCD_BL            14
#define CAN_TX            16
#define CAN_RX            15
#define BUZZER_PIN        38       // GPIO 19/20 = USB D-/D+; 38 is free PWM
#define XL95X5_CS         17
#define XL95X5_SCLK       15
#define XL95X5_MOSI       16
#define XL95X5_TOUCH_RST  4
#define XL95X5_LCD_RST    5
#define CST3240_ADDRESS   0x5A

// ───────── State ─────────
static float    g_backlight = 50.0f;
static uint8_t  g_r = 0, g_g = 0, g_b = 0;
static int16_t  g_last_touch_x = -1, g_last_touch_y = -1;
static bool     g_touch_pressed = false;

static volatile bool g_can_have_last = false;
static twai_message_t g_can_last;

struct ScoreNote { uint16_t freq_hz; uint16_t duration_ms; };
static ScoreNote g_score[64];
static uint8_t  g_score_len = 0;
static uint8_t  g_score_pos = 0;
static uint32_t g_score_next_ms = 0;
static bool     g_score_playing = false;

volatile bool Touch_Int_Flag = false;

// ───────── Display objects (mirror official Lvgl.ino) ─────────
TouchLib touch(Wire, IIC_SDA, IIC_SCL, CST3240_ADDRESS);

Arduino_DataBus *bus = new Arduino_XL9535SWSPI(
    IIC_SDA, IIC_SCL, -1, XL95X5_CS, XL95X5_SCLK, XL95X5_MOSI);
Arduino_ESP32RGBPanel *rgbpanel = new Arduino_ESP32RGBPanel(
    -1, LCD_VSYNC, LCD_HSYNC, LCD_PCLK,
    LCD_B0, LCD_B1, LCD_B2, LCD_B3, LCD_B4,
    LCD_G0, LCD_G1, LCD_G2, LCD_G3, LCD_G4, LCD_G5,
    LCD_R0, LCD_R1, LCD_R2, LCD_R3, LCD_R4,
    1 /* hsync_pol */, 20, 2, 0,
    1 /* vsync_pol */, 30, 8, 1,
    10 /* pclk_active_neg */, 6000000L /* PCLK 6MHz — official value */,
    false /* useBigEndian */, 0, 0);
Arduino_RGB_Display *gfx = new Arduino_RGB_Display(
    LCD_WIDTH, LCD_HEIGHT, rgbpanel, 0, true /* auto_flush */,
    bus, -1, st7701_type9_init_operations, sizeof(st7701_type9_init_operations));

// ───────── LVGL setup ─────────
static lv_disp_draw_buf_t draw_buf;
static lv_disp_drv_t  disp_drv;
static lv_indev_drv_t indev_drv;

static lv_obj_t *g_header_label;    // tiny device-id label, top-left
static lv_obj_t *g_status_label;    // dynamic "what are we doing now" bar
static lv_obj_t *g_text_labels[8];  // 8 message rows (0-3 narration, 4-7 LLM content)
static lv_obj_t *g_separator;       // horizontal line between narration and LLM area
static lv_obj_t *g_color_chip;      // small color indicator (set_color visualizer)
static lv_obj_t *g_footer_label;    // subtle bottom info bar

// Role → text color mapping for display_text. Lets the orchestrator
// color-code USER vs LLM vs DCP messages so the conversation flow is
// legible on the panel.
static lv_color_t role_to_color(const char* role, size_t len) {
    if      (len == 4 && memcmp(role, "user",    4) == 0) return lv_color_make(20, 150, 200);   // cyan
    else if (len == 3 && memcmp(role, "llm",     3) == 0) return lv_color_make(220, 160, 20);   // amber
    else if (len == 6 && memcmp(role, "dcp_ok",  6) == 0) return lv_color_make(30, 170, 60);    // green
    else if (len == 7 && memcmp(role, "dcp_err", 7) == 0) return lv_color_make(210, 40, 40);    // red
    else if (len == 7 && memcmp(role, "dcp_req", 7) == 0) return lv_color_make(110, 110, 130);  // gray
    return lv_color_black();
}

// Diagnostic: count flushes so we can detect runaway redraws.
static volatile uint32_t g_flush_count = 0;
static uint32_t g_last_flush_log_ms = 0;

static void my_disp_flush(lv_disp_drv_t *disp, const lv_area_t *area, lv_color_t *color_p) {
    uint32_t w = area->x2 - area->x1 + 1;
    uint32_t h = area->y2 - area->y1 + 1;
#if (LV_COLOR_16_SWAP != 0)
    gfx->draw16bitBeRGBBitmap(area->x1, area->y1, (uint16_t *)&color_p->full, w, h);
#else
    gfx->draw16bitRGBBitmap(area->x1, area->y1, (uint16_t *)&color_p->full, w, h);
#endif
    g_flush_count++;
    lv_disp_flush_ready(disp);
}

static void my_touchpad_read(lv_indev_drv_t *drv, lv_indev_data_t *data) {
    if (Touch_Int_Flag) {
        touch.read();
        TP_Point t = touch.getPoint(0);
        if (touch.getPointNum() == 1 && t.pressure > 0 && t.state != 0) {
            data->state = LV_INDEV_STATE_PR;
            data->point.x = t.x;
            data->point.y = t.y;
            g_touch_pressed = true;
            g_last_touch_x = t.x;
            g_last_touch_y = t.y;
        }
        Touch_Int_Flag = false;
    } else {
        data->state = LV_INDEV_STATE_REL;
        g_touch_pressed = false;
    }
}

// ───────── DCP intent handlers ─────────
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
    if (kind == dcp::KIND_DRY_RUN) { reply.add_float("would_set", level); return dcp::STATUS_OK; }
    g_backlight = (float)level;
    // Simple on/off backlight — official example just digitalWrites LCD_BL HIGH.
    digitalWrite(LCD_BL, level > 0 ? HIGH : LOW);
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
    // Tiny color chip on the status bar — a visual ack that set_color
    // landed without dominating screen real estate.
    if (g_color_chip) {
        lv_obj_set_style_bg_color(g_color_chip, lv_color_make(g_r, g_g, g_b), LV_PART_MAIN);
    }
    return dcp::STATUS_OK;
}

static dcp::Status h_display_text(uint8_t, dcp::CborReader& params,
                                  dcp::CborMap&, void*) {
    char buf[40] = {0};
    char role[12] = "plain";
    size_t role_len = 5;
    int64_t line = 0, size = 2;
    while (params.remaining() > 0) {
        const char* k; size_t kl;
        if (!params.next_key(&k, &kl)) return dcp::STATUS_DENIED;
        if (kl == 4 && memcmp(k, "text", 4) == 0) {
            const char* s; size_t slen;
            if (!params.read_string(&s, &slen)) return dcp::STATUS_RANGE;
            memcpy(buf, s, slen < 39 ? slen : 39);
        } else if (kl == 4 && memcmp(k, "line", 4) == 0) {
            if (!params.read_int(&line)) return dcp::STATUS_RANGE;
        } else if (kl == 4 && memcmp(k, "size", 4) == 0) {
            if (!params.read_int(&size)) return dcp::STATUS_RANGE;
        } else if (kl == 4 && memcmp(k, "role", 4) == 0) {
            const char* s; size_t slen;
            if (!params.read_string(&s, &slen)) return dcp::STATUS_RANGE;
            role_len = slen < sizeof(role) - 1 ? slen : sizeof(role) - 1;
            memcpy(role, s, role_len);
            role[role_len] = '\0';
        } else { params.skip(); }
    }
    if (line < 0 || line >= 8) return dcp::STATUS_RANGE;
    if (g_text_labels[line]) {
        lv_label_set_text(g_text_labels[line], buf);
        lv_obj_set_style_text_color(g_text_labels[line],
                                    role_to_color(role, role_len),
                                    LV_PART_MAIN);
    }
    return dcp::STATUS_OK;
}

static dcp::Status h_set_status(uint8_t, dcp::CborReader& params,
                                dcp::CborMap&, void*) {
    char buf[40] = {0};
    while (params.remaining() > 0) {
        const char* k; size_t kl;
        if (!params.next_key(&k, &kl)) return dcp::STATUS_DENIED;
        if (kl == 4 && memcmp(k, "text", 4) == 0) {
            const char* s; size_t slen;
            if (!params.read_string(&s, &slen)) return dcp::STATUS_RANGE;
            memcpy(buf, s, slen < 39 ? slen : 39);
        } else { params.skip(); }
    }
    if (g_status_label) lv_label_set_text(g_status_label, buf);
    return dcp::STATUS_OK;
}

static dcp::Status h_clear_screen(uint8_t, dcp::CborReader&, dcp::CborMap&, void*) {
    for (int i = 0; i < 8; i++) {
        if (g_text_labels[i]) {
            lv_label_set_text(g_text_labels[i], "");
            lv_obj_set_style_text_color(g_text_labels[i], lv_color_black(), LV_PART_MAIN);
        }
    }
    if (g_color_chip) {
        lv_obj_set_style_bg_color(g_color_chip, lv_color_make(40, 40, 50), LV_PART_MAIN);
    }
    g_r = g_g = g_b = 0;
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
    if (kind == dcp::KIND_DRY_RUN) { reply.add_int("would_play_hz", freq); return dcp::STATUS_OK; }
    tone(BUZZER_PIN, (uint32_t)freq, (uint32_t)duration);
    return dcp::STATUS_OK;
}

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
        int midi = 12 * (octave + 1) + chromatic + semitone_offset;
        freq_hz = (uint16_t)(440.0f * powf(2.0f, (midi - 69) / 12.0f));
    }
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
        reply.add_int("notes", g_score_len);
        reply.add_int("duration_ms", total_ms);
        g_score_len = 0;
        return dcp::STATUS_OK;
    }
    g_score_pos = 0;
    g_score_next_ms = millis();
    g_score_playing = true;
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
    if (kind == dcp::KIND_DRY_RUN) { reply.add_int("would_send_id", id); return dcp::STATUS_OK; }
    if (twai_transmit(&msg, pdMS_TO_TICKS(50)) != ESP_OK) return dcp::STATUS_BUSY;
    return dcp::STATUS_OK;
}

static dcp::Status h_can_receive_last(uint8_t, dcp::CborReader&,
                                      dcp::CborMap& reply, void*) {
    if (!g_can_have_last) { reply.add_string("value", ""); return dcp::STATUS_OK; }
    char buf[48];
    int n = snprintf(buf, sizeof(buf), "id=0x%x data=", (unsigned)g_can_last.identifier);
    for (int i = 0; i < g_can_last.data_length_code && n < (int)sizeof(buf) - 3; ++i) {
        n += snprintf(buf + n, sizeof(buf) - n, "%02x", g_can_last.data[i]);
    }
    reply.add_string("value", buf);
    return dcp::STATUS_OK;
}

static dcp::Status h_move_motor(uint8_t, dcp::CborReader&, dcp::CborMap&, void*) {
    return dcp::STATUS_DENIED;
}
static dcp::Status h_read_motor_position(uint8_t, dcp::CborReader&, dcp::CborMap&, void*) {
    return dcp::STATUS_DENIED;
}

static dcp::IntentBinding bindings[] = {
    { DCP_ID("set_backlight"),       h_set_backlight,       nullptr },
    { DCP_ID("set_color"),           h_set_color,           nullptr },
    { DCP_ID("display_text"),        h_display_text,        nullptr },
    { DCP_ID("set_status"),          h_set_status,          nullptr },
    { DCP_ID("clear_screen"),        h_clear_screen,        nullptr },
    { DCP_ID("play_tone"),           h_play_tone,           nullptr },
    { DCP_ID("play_score"),          h_play_score,          nullptr },
    { DCP_ID("stop_playback"),       h_stop_playback,       nullptr },
    { DCP_ID("read_touch"),          h_read_touch,          nullptr },
    { DCP_ID("can_send"),            h_can_send,            nullptr },
    { DCP_ID("can_receive_last"),    h_can_receive_last,    nullptr },
    { DCP_ID("move_motor"),          h_move_motor,          nullptr },
    { DCP_ID("read_motor_position"), h_read_motor_position, nullptr },
};
static dcp::DCP* dcp_link = nullptr;

// ───────── CAN / score / touch pumps ─────────
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
    }
}

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
    if (n.freq_hz == 0) noTone(BUZZER_PIN);
    else                tone(BUZZER_PIN, n.freq_hz);
    g_score_next_ms = now + n.duration_ms;
}

// ───────── LVGL UI ─────────
static void build_ui() {
    lv_obj_t *scr = lv_scr_act();
    lv_obj_set_style_bg_color(scr, lv_color_white(), LV_PART_MAIN);
    // Kill scrollbar/scroll on the screen too — it has the same fade behavior
    // as lv_obj_create children.
    lv_obj_clear_flag(scr, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_scrollbar_mode(scr, LV_SCROLLBAR_MODE_OFF);

    // y= 6: tiny device-id strip (always-on)
    g_header_label = lv_label_create(scr);
    lv_label_set_text(g_header_label, "DCP smart-panel-01");
    lv_obj_set_style_text_color(g_header_label, lv_color_make(110, 110, 130), LV_PART_MAIN);
    lv_obj_set_style_text_font(g_header_label, &lv_font_montserrat_14, LV_PART_MAIN);
    lv_obj_align(g_header_label, LV_ALIGN_TOP_LEFT, 10, 6);

    // y=28: STATUS BAR — dynamic "what scene we're on", dark slate banner.
    g_status_label = lv_label_create(scr);
    lv_label_set_text(g_status_label, "ready");
    lv_obj_set_width(g_status_label, LCD_WIDTH - 20);
    lv_obj_align(g_status_label, LV_ALIGN_TOP_LEFT, 10, 28);
    lv_obj_set_style_bg_color(g_status_label, lv_color_make(40, 50, 70), LV_PART_MAIN);
    lv_obj_set_style_bg_opa(g_status_label, LV_OPA_COVER, LV_PART_MAIN);
    lv_obj_set_style_text_color(g_status_label, lv_color_white(), LV_PART_MAIN);
    lv_obj_set_style_text_font(g_status_label, &lv_font_montserrat_14, LV_PART_MAIN);
    lv_obj_set_style_pad_all(g_status_label, 8, LV_PART_MAIN);
    lv_obj_clear_flag(g_status_label, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_scrollbar_mode(g_status_label, LV_SCROLLBAR_MODE_OFF);

    // Tiny color chip on the right of the status bar — visualizes set_color.
    g_color_chip = lv_obj_create(scr);
    lv_obj_set_size(g_color_chip, 28, 28);
    lv_obj_align(g_color_chip, LV_ALIGN_TOP_RIGHT, -16, 32);
    lv_obj_set_style_bg_color(g_color_chip, lv_color_make(40, 40, 50), LV_PART_MAIN);
    lv_obj_set_style_border_color(g_color_chip, lv_color_white(), LV_PART_MAIN);
    lv_obj_set_style_border_width(g_color_chip, 1, LV_PART_MAIN);
    lv_obj_clear_flag(g_color_chip, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_scrollbar_mode(g_color_chip, LV_SCROLLBAR_MODE_OFF);

    // y= 80..248: lines 0-3 = orchestrator narration zone
    //   line 0 USER (cyan), line 1 LLM (amber), line 2 DCP-status (green/red),
    //   line 3 DCP-detail (small data)
    for (int i = 0; i < 4; i++) {
        g_text_labels[i] = lv_label_create(scr);
        lv_label_set_text(g_text_labels[i], "");
        lv_obj_set_style_text_color(g_text_labels[i], lv_color_black(), LV_PART_MAIN);
        lv_obj_set_style_text_font(g_text_labels[i], &lv_font_montserrat_14, LV_PART_MAIN);
        lv_obj_align(g_text_labels[i], LV_ALIGN_TOP_LEFT, 10, 80 + i * 36);
    }

    // y=240: separator line between narration (above) and LLM content (below)
    g_separator = lv_obj_create(scr);
    lv_obj_set_size(g_separator, LCD_WIDTH - 40, 2);
    lv_obj_align(g_separator, LV_ALIGN_TOP_MID, 0, 240);
    lv_obj_set_style_bg_color(g_separator, lv_color_make(190, 195, 210), LV_PART_MAIN);
    lv_obj_set_style_border_width(g_separator, 0, LV_PART_MAIN);
    lv_obj_clear_flag(g_separator, LV_OBJ_FLAG_SCROLLABLE);

    // y=256..400: lines 4-7 = LLM's free content area
    for (int i = 4; i < 8; i++) {
        g_text_labels[i] = lv_label_create(scr);
        lv_label_set_text(g_text_labels[i], "");
        lv_obj_set_style_text_color(g_text_labels[i], lv_color_black(), LV_PART_MAIN);
        lv_obj_set_style_text_font(g_text_labels[i], &lv_font_montserrat_14, LV_PART_MAIN);
        lv_obj_align(g_text_labels[i], LV_ALIGN_TOP_LEFT, 10, 256 + (i - 4) * 36);
    }

    // y=440: subtle footer "model: DeepSeek-V3  |  manifest v0.3.1  |  12 intents"
    g_footer_label = lv_label_create(scr);
    lv_label_set_text(g_footer_label, "DCP v0.3.1  |  12 intents  |  CBOR/UART");
    lv_obj_set_style_text_color(g_footer_label, lv_color_make(150, 150, 165), LV_PART_MAIN);
    lv_obj_set_style_text_font(g_footer_label, &lv_font_montserrat_14, LV_PART_MAIN);
    lv_obj_align(g_footer_label, LV_ALIGN_BOTTOM_LEFT, 10, -8);
}

static void lvgl_init_displays() {
    lv_init();

    uint32_t W = gfx->width(), H = gfx->height();

    // Official sample allocates draw buffers with MALLOC_CAP_INTERNAL.
    lv_color_t *buf1 = (lv_color_t *)heap_caps_malloc(
        sizeof(lv_color_t) * LCD_WIDTH * 40, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    lv_color_t *buf2 = (lv_color_t *)heap_caps_malloc(
        sizeof(lv_color_t) * LCD_WIDTH * 40, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    while (!buf1 || !buf2) {
        Serial.println("LVGL draw buf alloc failed!");
        delay(1000);
    }
    lv_disp_draw_buf_init(&draw_buf, buf1, buf2, LCD_WIDTH * 40);

    lv_disp_drv_init(&disp_drv);
    disp_drv.hor_res = W;
    disp_drv.ver_res = H;
    disp_drv.flush_cb = my_disp_flush;
    disp_drv.draw_buf = &draw_buf;
    // full_refresh=0 (default): only redraw dirty regions. With static
    // widgets and DCP-driven updates, the panel goes idle between events
    // → no continuous repaint → no visible flicker.
    disp_drv.full_refresh = 0;
    lv_disp_drv_register(&disp_drv);

    lv_indev_drv_init(&indev_drv);
    indev_drv.type = LV_INDEV_TYPE_POINTER;
    indev_drv.read_cb = my_touchpad_read;
    lv_indev_drv_register(&indev_drv);
}

// ───────── Setup / loop ─────────
void setup() {
    Serial.begin(115200);
    delay(2000);
    Serial.println("[1] setup start");

    pinMode(LCD_BL, OUTPUT);
    digitalWrite(LCD_BL, HIGH);
    pinMode(BUZZER_PIN, OUTPUT);

    attachInterrupt(TOUCH_INT, [] { Touch_Int_Flag = true; }, FALLING);

    Wire.begin(IIC_SDA, IIC_SCL);
    Serial.println("[2] Wire begin");

    gfx->begin();
    gfx->fillScreen(BLACK);
    Serial.println("[3] gfx->begin done");

    // Reset touch via the XL9535 expander API
    gfx->XL_digitalWrite(XL95X5_TOUCH_RST, LOW);
    delay(200);
    gfx->XL_digitalWrite(XL95X5_TOUCH_RST, HIGH);
    delay(200);

    touch.init();
    Serial.println("[4] touch init done");

    lvgl_init_displays();
    Serial.println("[5] LVGL init done");

    build_ui();
    Serial.println("[6] UI built");

    init_can();
    Serial.println("[7] CAN init done");

    static dcp::DCP link(Serial, bindings, sizeof(bindings) / sizeof(bindings[0]));
    dcp_link = &link;
    Serial.println("[8] DCP link up — entering loop");
}

void loop() {
    if (dcp_link) dcp_link->poll();
    pump_can();
    pump_score();

    // LVGL needs to know how much time elapsed since last tick. The bundled
    // lv_conf.h has LV_TICK_CUSTOM=0, so we feed it manually here. Without
    // this, lv_timer_handler thinks no time has passed and the refresh
    // timer never fires → dirty widgets never reach flush_cb → no on-screen
    // updates after the first paint.
    static uint32_t last_tick_ms = 0;
    uint32_t now = millis();
    lv_tick_inc(now - last_tick_ms);
    last_tick_ms = now;

    lv_timer_handler();
    delay(5);
}
