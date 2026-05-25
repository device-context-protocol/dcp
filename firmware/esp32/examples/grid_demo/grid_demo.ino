// Grid Demo — visual DCP capability/range gating demo on LilyGo T-Panel S3.
//
// A 6×6 grid is drawn in the middle of the panel; a green square sits in
// one cell. The LLM gets a single tool: move(direction, steps). The DCP
// firmware checks bounds in the move handler — if the move would leave
// the grid, it flashes the grid red, shows a dashed-red "✗" ghost at the
// attempted cell, and returns STATUS_RANGE. The square never moves on
// rejected calls. Audience grok: "square moved" vs "square didn't move,
// grid flashed red". No protocol jargon needed.
//
// Mirrors web/panel-emu — iterate UX there, port here.
//
// Build target: Arduino-ESP32 2.0.14 + Arduino_GFX 1.4.6 + LVGL 8.3.5.

#include "DCP.h"
#include "DCPCrypto.h"
#include <Arduino.h>
#include <Wire.h>
#include <lvgl.h>
#include <Arduino_GFX_Library.h>
#define TOUCH_MODULES_CST_MUTUAL
#include "TouchLib.h"

// ───────── Pin defs (same as smart_panel) ─────────
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
#define XL95X5_CS         17
#define XL95X5_SCLK       15
#define XL95X5_MOSI       16
#define XL95X5_TOUCH_RST  4
#define CST3240_ADDRESS   0x5A

// ───────── Grid layout ─────────
constexpr int GRID_COLS    = 6;
constexpr int GRID_ROWS    = 6;
constexpr int GRID_CELL    = 40;
constexpr int GRID_W       = GRID_CELL * GRID_COLS;     // 240
constexpr int GRID_H       = GRID_CELL * GRID_ROWS;     // 240
constexpr int GRID_ORIG_X  = (LCD_WIDTH - GRID_W) / 2;  // 120
constexpr int GRID_ORIG_Y  = 168;
constexpr int SQUARE_INSET = 4;                          // square padding inside cell
constexpr int SQUARE_PX    = GRID_CELL - SQUARE_INSET * 2;

// ───────── State ─────────
static int g_x = 0, g_y = 0;
volatile bool Touch_Int_Flag = false;

// ───────── Display objects ─────────
TouchLib touch(Wire, IIC_SDA, IIC_SCL, CST3240_ADDRESS);
Arduino_DataBus *bus = new Arduino_XL9535SWSPI(
    IIC_SDA, IIC_SCL, -1, XL95X5_CS, XL95X5_SCLK, XL95X5_MOSI);
Arduino_ESP32RGBPanel *rgbpanel = new Arduino_ESP32RGBPanel(
    -1, LCD_VSYNC, LCD_HSYNC, LCD_PCLK,
    LCD_B0, LCD_B1, LCD_B2, LCD_B3, LCD_B4,
    LCD_G0, LCD_G1, LCD_G2, LCD_G3, LCD_G4, LCD_G5,
    LCD_R0, LCD_R1, LCD_R2, LCD_R3, LCD_R4,
    1, 20, 2, 0,
    1, 30, 8, 1,
    10, 6000000L, false, 0, 0);
Arduino_RGB_Display *gfx = new Arduino_RGB_Display(
    LCD_WIDTH, LCD_HEIGHT, rgbpanel, 0, true,
    bus, -1, st7701_type9_init_operations, sizeof(st7701_type9_init_operations));

// ───────── LVGL ─────────
static lv_disp_draw_buf_t draw_buf;
static lv_disp_drv_t  disp_drv;
static lv_indev_drv_t indev_drv;

static lv_obj_t *g_header_label;
static lv_obj_t *g_status_label;
static lv_obj_t *g_text_labels[3];      // 3 narration rows: USER / LLM / DCP
static lv_obj_t *g_grid_container;
static lv_obj_t *g_square;
static lv_obj_t *g_ghost;
static lv_obj_t *g_ghost_x_label;
static lv_obj_t *g_pos_label;
static lv_obj_t *g_footer_label;

static lv_color_t role_to_color(const char* role, size_t len) {
    if      (len == 4 && memcmp(role, "user",    4) == 0) return lv_color_make(20, 150, 200);
    else if (len == 3 && memcmp(role, "llm",     3) == 0) return lv_color_make(220, 160, 20);
    else if (len == 6 && memcmp(role, "dcp_ok",  6) == 0) return lv_color_make(30, 170, 60);
    else if (len == 7 && memcmp(role, "dcp_err", 7) == 0) return lv_color_make(210, 40, 40);
    else if (len == 7 && memcmp(role, "dcp_req", 7) == 0) return lv_color_make(110, 110, 130);
    return lv_color_black();
}

static void my_disp_flush(lv_disp_drv_t *disp, const lv_area_t *area, lv_color_t *color_p) {
    uint32_t w = area->x2 - area->x1 + 1;
    uint32_t h = area->y2 - area->y1 + 1;
#if (LV_COLOR_16_SWAP != 0)
    gfx->draw16bitBeRGBBitmap(area->x1, area->y1, (uint16_t *)&color_p->full, w, h);
#else
    gfx->draw16bitRGBBitmap(area->x1, area->y1, (uint16_t *)&color_p->full, w, h);
#endif
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
        }
        Touch_Int_Flag = false;
    } else {
        data->state = LV_INDEV_STATE_REL;
    }
}

// ───────── Square move animation ─────────
static void square_anim_x_cb(void* var, int32_t v) { lv_obj_set_x((lv_obj_t*)var, v); }
static void square_anim_y_cb(void* var, int32_t v) { lv_obj_set_y((lv_obj_t*)var, v); }

static void square_move_to(int new_x, int new_y) {
    int target_px_x = new_x * GRID_CELL + SQUARE_INSET;
    int target_px_y = new_y * GRID_CELL + SQUARE_INSET;
    int cur_x = lv_obj_get_x(g_square);
    int cur_y = lv_obj_get_y(g_square);

    lv_anim_t ax; lv_anim_init(&ax);
    lv_anim_set_var(&ax, g_square);
    lv_anim_set_exec_cb(&ax, square_anim_x_cb);
    lv_anim_set_values(&ax, cur_x, target_px_x);
    lv_anim_set_time(&ax, 250);
    lv_anim_set_path_cb(&ax, lv_anim_path_ease_out);
    lv_anim_start(&ax);

    lv_anim_t ay; lv_anim_init(&ay);
    lv_anim_set_var(&ay, g_square);
    lv_anim_set_exec_cb(&ay, square_anim_y_cb);
    lv_anim_set_values(&ay, cur_y, target_px_y);
    lv_anim_set_time(&ay, 250);
    lv_anim_set_path_cb(&ay, lv_anim_path_ease_out);
    lv_anim_start(&ay);

    g_x = new_x;
    g_y = new_y;
}

// ───────── Flash + ghost timers ─────────
// Use OUTLINE (drawn outside the widget, no layout impact) for the flash
// ring — changing border-width would push the internal cells inward and
// cause visible jitter on the grid.
static void flash_revert_cb(lv_timer_t* t) {
    lv_obj_set_style_outline_opa(g_grid_container, LV_OPA_TRANSP, LV_PART_MAIN);
    lv_timer_del(t);
}

static void ghost_hide_cb(lv_timer_t* t) {
    if (g_ghost) lv_obj_add_flag(g_ghost, LV_OBJ_FLAG_HIDDEN);
    lv_timer_del(t);
}

static void flash_grid(bool err, uint32_t hold_ms) {
    lv_color_t c = err ? lv_color_make(220, 40, 40) : lv_color_make(40, 200, 80);
    lv_obj_set_style_outline_color(g_grid_container, c, LV_PART_MAIN);
    lv_obj_set_style_outline_width(g_grid_container, 4, LV_PART_MAIN);
    lv_obj_set_style_outline_opa(g_grid_container, LV_OPA_COVER, LV_PART_MAIN);
    lv_timer_t* t = lv_timer_create(flash_revert_cb, hold_ms, nullptr);
    lv_timer_set_repeat_count(t, 1);
}

static void show_ghost(int gx, int gy, uint32_t hold_ms) {
    // Clip into the visible grid for display purposes (can't draw outside)
    if (gx < 0) gx = 0; if (gx > GRID_COLS - 1) gx = GRID_COLS - 1;
    if (gy < 0) gy = 0; if (gy > GRID_ROWS - 1) gy = GRID_ROWS - 1;
    lv_obj_set_pos(g_ghost, gx * GRID_CELL + SQUARE_INSET, gy * GRID_CELL + SQUARE_INSET);
    lv_obj_clear_flag(g_ghost, LV_OBJ_FLAG_HIDDEN);
    lv_timer_t* t = lv_timer_create(ghost_hide_cb, hold_ms, nullptr);
    lv_timer_set_repeat_count(t, 1);
}

static void update_pos_label() {
    if (!g_pos_label) return;
    char buf[40];
    snprintf(buf, sizeof(buf), "%dx%d  (%d,%d)", GRID_COLS, GRID_ROWS, g_x, g_y);
    lv_label_set_text(g_pos_label, buf);
}

// ───────── DCP intent handlers ─────────

// move(direction: "up"|"down"|"left"|"right", steps: int [1, GRID_COLS+1])
// If in-bounds: animate move, flash green, return ok.
// If out-of-bounds: show red ghost at attempted cell, flash red, return range.
static dcp::Status h_move(uint8_t kind, dcp::CborReader& params,
                          dcp::CborMap& reply, void*) {
    char dir[8] = {0};
    size_t dir_len = 0;
    int64_t steps = 1;
    while (params.remaining() > 0) {
        const char* k; size_t kl;
        if (!params.next_key(&k, &kl)) return dcp::STATUS_DENIED;
        if (kl == 9 && memcmp(k, "direction", 9) == 0) {
            const char* s; size_t slen;
            if (!params.read_string(&s, &slen)) return dcp::STATUS_RANGE;
            dir_len = slen < sizeof(dir) - 1 ? slen : sizeof(dir) - 1;
            memcpy(dir, s, dir_len); dir[dir_len] = '\0';
        } else if (kl == 5 && memcmp(k, "steps", 5) == 0) {
            if (!params.read_int(&steps)) return dcp::STATUS_RANGE;
        } else { params.skip(); }
    }
    if (steps < 1 || steps > GRID_COLS + 1) return dcp::STATUS_RANGE;

    int dx = 0, dy = 0;
    if      (dir_len == 5 && memcmp(dir, "right", 5) == 0) dx =  (int)steps;
    else if (dir_len == 4 && memcmp(dir, "left",  4) == 0) dx = -(int)steps;
    else if (dir_len == 4 && memcmp(dir, "down",  4) == 0) dy =  (int)steps;
    else if (dir_len == 2 && memcmp(dir, "up",    2) == 0) dy = -(int)steps;
    else return dcp::STATUS_RANGE;

    int nx = g_x + dx;
    int ny = g_y + dy;

    if (kind == dcp::KIND_DRY_RUN) {
        reply.add_int("would_x", nx);
        reply.add_int("would_y", ny);
        reply.add_bool("in_bounds", nx >= 0 && nx < GRID_COLS && ny >= 0 && ny < GRID_ROWS);
        return dcp::STATUS_OK;
    }

    bool oob = (nx < 0 || nx >= GRID_COLS || ny < 0 || ny >= GRID_ROWS);
    if (oob) {
        // Show ghost where they tried (clipped to edge) + red flash
        show_ghost(nx, ny, 2200);
        flash_grid(/*err=*/true, 1200);
        reply.add_int("attempted_x", nx);
        reply.add_int("attempted_y", ny);
        return dcp::STATUS_RANGE;
    }

    square_move_to(nx, ny);
    flash_grid(/*err=*/false, 250);
    update_pos_label();
    reply.add_int("x", nx);
    reply.add_int("y", ny);
    return dcp::STATUS_OK;
}

static dcp::Status h_grid_reset(uint8_t, dcp::CborReader& params,
                                dcp::CborMap&, void*) {
    int64_t x = 0, y = 0;
    while (params.remaining() > 0) {
        const char* k; size_t kl;
        if (!params.next_key(&k, &kl)) return dcp::STATUS_DENIED;
        if      (kl == 1 && k[0] == 'x') { if (!params.read_int(&x)) return dcp::STATUS_RANGE; }
        else if (kl == 1 && k[0] == 'y') { if (!params.read_int(&y)) return dcp::STATUS_RANGE; }
        else                              { params.skip(); }
    }
    if (x < 0 || x >= GRID_COLS || y < 0 || y >= GRID_ROWS) return dcp::STATUS_RANGE;
    g_x = (int)x; g_y = (int)y;
    lv_obj_set_pos(g_square, g_x * GRID_CELL + SQUARE_INSET, g_y * GRID_CELL + SQUARE_INSET);
    update_pos_label();
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

static dcp::Status h_narrate(uint8_t, dcp::CborReader& params,
                             dcp::CborMap&, void*) {
    char buf[40] = {0};
    char role[12] = "plain"; size_t role_len = 5;
    int64_t line = 0;
    while (params.remaining() > 0) {
        const char* k; size_t kl;
        if (!params.next_key(&k, &kl)) return dcp::STATUS_DENIED;
        if (kl == 4 && memcmp(k, "text", 4) == 0) {
            const char* s; size_t slen;
            if (!params.read_string(&s, &slen)) return dcp::STATUS_RANGE;
            memcpy(buf, s, slen < 39 ? slen : 39);
        } else if (kl == 4 && memcmp(k, "line", 4) == 0) {
            if (!params.read_int(&line)) return dcp::STATUS_RANGE;
        } else if (kl == 4 && memcmp(k, "role", 4) == 0) {
            const char* s; size_t slen;
            if (!params.read_string(&s, &slen)) return dcp::STATUS_RANGE;
            role_len = slen < sizeof(role) - 1 ? slen : sizeof(role) - 1;
            memcpy(role, s, role_len); role[role_len] = '\0';
        } else { params.skip(); }
    }
    if (line < 0 || line >= 3) return dcp::STATUS_RANGE;
    if (g_text_labels[line]) {
        lv_label_set_text(g_text_labels[line], buf);
        lv_obj_set_style_text_color(g_text_labels[line], role_to_color(role, role_len), LV_PART_MAIN);
    }
    return dcp::STATUS_OK;
}

static dcp::Status h_clear_narration(uint8_t, dcp::CborReader&, dcp::CborMap&, void*) {
    for (int i = 0; i < 3; i++) {
        if (g_text_labels[i]) {
            lv_label_set_text(g_text_labels[i], "");
            lv_obj_set_style_text_color(g_text_labels[i], lv_color_black(), LV_PART_MAIN);
        }
    }
    return dcp::STATUS_OK;
}

static dcp::IntentBinding bindings[] = {
    { DCP_ID("move"),            h_move,            nullptr },
    { DCP_ID("grid_reset"),      h_grid_reset,      nullptr },
    { DCP_ID("set_status"),      h_set_status,      nullptr },
    { DCP_ID("narrate"),         h_narrate,         nullptr },
    { DCP_ID("clear_narration"), h_clear_narration, nullptr },
};
static dcp::DCP* dcp_link = nullptr;

// ───────── UI build ─────────
static void build_ui() {
    lv_obj_t *scr = lv_scr_act();
    lv_obj_set_style_bg_color(scr, lv_color_white(), LV_PART_MAIN);
    lv_obj_clear_flag(scr, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_scrollbar_mode(scr, LV_SCROLLBAR_MODE_OFF);

    // device-id strip
    g_header_label = lv_label_create(scr);
    lv_label_set_text(g_header_label, "DCP grid-demo-01");
    lv_obj_set_style_text_color(g_header_label, lv_color_make(110, 110, 130), LV_PART_MAIN);
    lv_obj_set_style_text_font(g_header_label, &lv_font_montserrat_14, LV_PART_MAIN);
    lv_obj_align(g_header_label, LV_ALIGN_TOP_LEFT, 10, 6);

    // status bar (full width now)
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

    // 3 narration rows: USER / LLM / DCP
    for (int i = 0; i < 3; i++) {
        g_text_labels[i] = lv_label_create(scr);
        lv_label_set_text(g_text_labels[i], "");
        lv_obj_set_style_text_color(g_text_labels[i], lv_color_black(), LV_PART_MAIN);
        lv_obj_set_style_text_font(g_text_labels[i], &lv_font_montserrat_14, LV_PART_MAIN);
        lv_obj_align(g_text_labels[i], LV_ALIGN_TOP_LEFT, 10, 72 + i * 28);
    }

    // Grid container — 288×288 centered horizontally
    g_grid_container = lv_obj_create(scr);
    lv_obj_set_size(g_grid_container, GRID_W, GRID_H);
    lv_obj_set_pos(g_grid_container, GRID_ORIG_X, GRID_ORIG_Y);
    lv_obj_set_style_bg_color(g_grid_container, lv_color_white(), LV_PART_MAIN);
    lv_obj_set_style_border_color(g_grid_container, lv_color_make(200, 205, 215), LV_PART_MAIN);
    lv_obj_set_style_border_width(g_grid_container, 1, LV_PART_MAIN);
    lv_obj_set_style_pad_all(g_grid_container, 0, LV_PART_MAIN);
    lv_obj_set_style_radius(g_grid_container, 4, LV_PART_MAIN);
    lv_obj_clear_flag(g_grid_container, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_scrollbar_mode(g_grid_container, LV_SCROLLBAR_MODE_OFF);

    // Cell borders — one lv_obj per cell, thin gray border
    for (int row = 0; row < GRID_ROWS; row++) {
        for (int col = 0; col < GRID_COLS; col++) {
            lv_obj_t *cell = lv_obj_create(g_grid_container);
            lv_obj_set_size(cell, GRID_CELL, GRID_CELL);
            lv_obj_set_pos(cell, col * GRID_CELL, row * GRID_CELL);
            lv_obj_set_style_bg_opa(cell, LV_OPA_TRANSP, LV_PART_MAIN);
            lv_obj_set_style_border_color(cell, lv_color_make(225, 228, 235), LV_PART_MAIN);
            lv_obj_set_style_border_width(cell, 1, LV_PART_MAIN);
            lv_obj_set_style_radius(cell, 0, LV_PART_MAIN);
            lv_obj_set_style_pad_all(cell, 0, LV_PART_MAIN);
            lv_obj_clear_flag(cell, LV_OBJ_FLAG_SCROLLABLE);
            lv_obj_set_scrollbar_mode(cell, LV_SCROLLBAR_MODE_OFF);
        }
    }

    // Ghost (hidden by default) — red bordered ✗ marker
    g_ghost = lv_obj_create(g_grid_container);
    lv_obj_set_size(g_ghost, SQUARE_PX, SQUARE_PX);
    lv_obj_set_pos(g_ghost, SQUARE_INSET, SQUARE_INSET);
    lv_obj_set_style_bg_opa(g_ghost, LV_OPA_TRANSP, LV_PART_MAIN);
    lv_obj_set_style_border_color(g_ghost, lv_color_make(220, 40, 40), LV_PART_MAIN);
    lv_obj_set_style_border_width(g_ghost, 2, LV_PART_MAIN);
    lv_obj_set_style_radius(g_ghost, 2, LV_PART_MAIN);
    lv_obj_set_style_pad_all(g_ghost, 0, LV_PART_MAIN);
    lv_obj_add_flag(g_ghost, LV_OBJ_FLAG_HIDDEN);
    lv_obj_clear_flag(g_ghost, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_scrollbar_mode(g_ghost, LV_SCROLLBAR_MODE_OFF);

    g_ghost_x_label = lv_label_create(g_ghost);
    lv_label_set_text(g_ghost_x_label, "X");
    lv_obj_set_style_text_color(g_ghost_x_label, lv_color_make(220, 40, 40), LV_PART_MAIN);
    lv_obj_set_style_text_font(g_ghost_x_label, &lv_font_montserrat_14, LV_PART_MAIN);
    lv_obj_center(g_ghost_x_label);

    // Square — green block
    g_square = lv_obj_create(g_grid_container);
    lv_obj_set_size(g_square, SQUARE_PX, SQUARE_PX);
    lv_obj_set_pos(g_square, g_x * GRID_CELL + SQUARE_INSET, g_y * GRID_CELL + SQUARE_INSET);
    lv_obj_set_style_bg_color(g_square, lv_color_make(40, 200, 80), LV_PART_MAIN);
    lv_obj_set_style_border_color(g_square, lv_color_make(20, 140, 60), LV_PART_MAIN);
    lv_obj_set_style_border_width(g_square, 2, LV_PART_MAIN);
    lv_obj_set_style_radius(g_square, 4, LV_PART_MAIN);
    lv_obj_set_style_pad_all(g_square, 0, LV_PART_MAIN);
    lv_obj_clear_flag(g_square, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_scrollbar_mode(g_square, LV_SCROLLBAR_MODE_OFF);

    // Position read-out below grid — sits just under the grid (y=408+8=416)
    g_pos_label = lv_label_create(scr);
    lv_label_set_text(g_pos_label, "");
    lv_obj_set_style_text_color(g_pos_label, lv_color_make(100, 105, 120), LV_PART_MAIN);
    lv_obj_set_style_text_font(g_pos_label, &lv_font_montserrat_14, LV_PART_MAIN);
    lv_obj_set_pos(g_pos_label, 0, GRID_ORIG_Y + GRID_H + 8);
    lv_obj_set_width(g_pos_label, LCD_WIDTH);
    lv_obj_set_style_text_align(g_pos_label, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN);
    update_pos_label();

    // Footer at very bottom — uses | instead of · because · isn't in the
    // default montserrat_14 glyph set.
    g_footer_label = lv_label_create(scr);
    lv_label_set_text(g_footer_label, "DCP grid demo   |   move(dir, steps)");
    lv_obj_set_style_text_color(g_footer_label, lv_color_make(150, 150, 165), LV_PART_MAIN);
    lv_obj_set_style_text_font(g_footer_label, &lv_font_montserrat_14, LV_PART_MAIN);
    lv_obj_align(g_footer_label, LV_ALIGN_BOTTOM_MID, 0, -10);
}

static void lvgl_init_displays() {
    lv_init();
    lv_color_t *buf1 = (lv_color_t *)heap_caps_malloc(
        sizeof(lv_color_t) * LCD_WIDTH * 40, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    lv_color_t *buf2 = (lv_color_t *)heap_caps_malloc(
        sizeof(lv_color_t) * LCD_WIDTH * 40, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    while (!buf1 || !buf2) { Serial.println("buf alloc failed"); delay(1000); }
    lv_disp_draw_buf_init(&draw_buf, buf1, buf2, LCD_WIDTH * 40);

    lv_disp_drv_init(&disp_drv);
    disp_drv.hor_res = LCD_WIDTH;
    disp_drv.ver_res = LCD_HEIGHT;
    disp_drv.flush_cb = my_disp_flush;
    disp_drv.draw_buf = &draw_buf;
    disp_drv.full_refresh = 0;
    lv_disp_drv_register(&disp_drv);

    lv_indev_drv_init(&indev_drv);
    indev_drv.type    = LV_INDEV_TYPE_POINTER;
    indev_drv.read_cb = my_touchpad_read;
    lv_indev_drv_register(&indev_drv);
}

void setup() {
    Serial.begin(115200);
    delay(2000);
    Serial.println("[1] setup start");

    pinMode(LCD_BL, OUTPUT);
    digitalWrite(LCD_BL, HIGH);
    attachInterrupt(TOUCH_INT, [] { Touch_Int_Flag = true; }, FALLING);

    Wire.begin(IIC_SDA, IIC_SCL);
    gfx->begin();
    gfx->fillScreen(BLACK);

    gfx->XL_digitalWrite(XL95X5_TOUCH_RST, LOW);  delay(200);
    gfx->XL_digitalWrite(XL95X5_TOUCH_RST, HIGH); delay(200);
    touch.init();
    Serial.println("[2] touch ready");

    lvgl_init_displays();
    build_ui();
    Serial.println("[3] UI built");

    static dcp::DCP link(Serial, bindings, sizeof(bindings) / sizeof(bindings[0]));
    dcp_link = &link;
    Serial.println("[4] DCP link up — entering loop");
}

void loop() {
    if (dcp_link) dcp_link->poll();

    static uint32_t last_tick_ms = 0;
    uint32_t now = millis();
    lv_tick_inc(now - last_tick_ms);
    last_tick_ms = now;

    lv_timer_handler();
    delay(5);
}
