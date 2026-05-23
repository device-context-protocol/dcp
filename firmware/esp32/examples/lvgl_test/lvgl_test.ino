// Minimal LVGL hello-world on LILYGO T-Panel S3.
//
// Goal: validate that LVGL's partial-buffer + flush-callback model
// renders cleanly on this board, side-stepping the bounce-buffer
// ping-pong artifact we hit when drawing through Arduino_GFX's
// PSRAM frame buffer directly.
//
// Carries forward the discoveries from smart_panel.ino:
// - XL9535 needs both ports forced OUTPUT + LCD_RST pulse before gfx->begin
// - Custom ST7701 init: type9 byte sequence with COLMOD (0x3A) = 0x50
//   for RGB565 instead of the library's default 0x60 (RGB666)
//
// Build: ESP32S3 Dev Module, Flash 16MB, PSRAM enabled (QSPI),
//        USB Mode = hwcdc, CDC on Boot = enabled

#include <Arduino.h>
#include <Wire.h>
#include <lvgl.h>
#define TOUCH_MODULES_CST_MUTUAL
#include "TouchLib.h"
#include <Arduino_GFX_Library.h>

// ───── Pin definitions ─────
#define IIC_SDA       17
#define IIC_SCL       18
#define TOUCH_INT     21
#define LCD_WIDTH     480
#define LCD_HEIGHT    480
#define LCD_BL        14
#define XL95X5_CS         17
#define XL95X5_SCLK       15
#define XL95X5_MOSI       16
#define XL95X5_LCD_RST    5
#define CST3240_ADDR      0x5A

// ───── Custom ST7701 init: type9 with COLMOD=0x50 (RGB565) ─────
static const uint8_t st7701_rgb565_init[] = {
    BEGIN_WRITE,
    WRITE_COMMAND_8, 0xFF,
    WRITE_BYTES, 5, 0x77, 0x01, 0x00, 0x00, 0x10,
    WRITE_C8_D16, 0xC0, 0x3B, 0x00,
    WRITE_C8_D16, 0xC1, 0x0D, 0x02,
    WRITE_C8_D16, 0xC2, 0x31, 0x05,
    WRITE_C8_D8, 0xCD, 0x00,
    WRITE_COMMAND_8, 0xB0,
    WRITE_BYTES, 16,
    0x00, 0x11, 0x18, 0x0E, 0x11, 0x06, 0x07, 0x08,
    0x07, 0x22, 0x04, 0x12, 0x0F, 0xAA, 0x31, 0x18,
    WRITE_COMMAND_8, 0xB1,
    WRITE_BYTES, 16,
    0x00, 0x11, 0x19, 0x0E, 0x12, 0x07, 0x08, 0x08,
    0x08, 0x22, 0x04, 0x11, 0x11, 0xA9, 0x32, 0x18,
    WRITE_COMMAND_8, 0xFF,
    WRITE_BYTES, 5, 0x77, 0x01, 0x00, 0x00, 0x11,
    WRITE_C8_D8, 0xB0, 0x60, WRITE_C8_D8, 0xB1, 0x32,
    WRITE_C8_D8, 0xB2, 0x07, WRITE_C8_D8, 0xB3, 0x80,
    WRITE_C8_D8, 0xB5, 0x49, WRITE_C8_D8, 0xB7, 0x85,
    WRITE_C8_D8, 0xB8, 0x21, WRITE_C8_D8, 0xC1, 0x78,
    WRITE_C8_D8, 0xC2, 0x78,
    WRITE_COMMAND_8, 0xE0,
    WRITE_BYTES, 3, 0x00, 0x1B, 0x02,
    WRITE_COMMAND_8, 0xE1,
    WRITE_BYTES, 11,
    0x08, 0xA0, 0x00, 0x00, 0x07, 0xA0, 0x00, 0x00, 0x00, 0x44, 0x44,
    WRITE_COMMAND_8, 0xE2,
    WRITE_BYTES, 12,
    0x11, 0x11, 0x44, 0x44, 0xED, 0xA0, 0x00, 0x00, 0xEC, 0xA0, 0x00, 0x00,
    WRITE_COMMAND_8, 0xE3,
    WRITE_BYTES, 4, 0x00, 0x00, 0x11, 0x11,
    WRITE_C8_D16, 0xE4, 0x44, 0x44,
    WRITE_COMMAND_8, 0xE5,
    WRITE_BYTES, 16,
    0x0A, 0xE9, 0xD8, 0xA0, 0x0C, 0xEB, 0xD8, 0xA0,
    0x0E, 0xED, 0xD8, 0xA0, 0x10, 0xEF, 0xD8, 0xA0,
    WRITE_COMMAND_8, 0xE6,
    WRITE_BYTES, 4, 0x00, 0x00, 0x11, 0x11,
    WRITE_C8_D16, 0xE7, 0x44, 0x44,
    WRITE_COMMAND_8, 0xE8,
    WRITE_BYTES, 16,
    0x09, 0xE8, 0xD8, 0xA0, 0x0B, 0xEA, 0xD8, 0xA0,
    0x0D, 0xEC, 0xD8, 0xA0, 0x0F, 0xEE, 0xD8, 0xA0,
    WRITE_COMMAND_8, 0xEB,
    WRITE_BYTES, 7,
    0x02, 0x00, 0xE4, 0xE4, 0x88, 0x00, 0x40,
    WRITE_C8_D16, 0xEC, 0x3C, 0x00,
    WRITE_COMMAND_8, 0xED,
    WRITE_BYTES, 16,
    0xAB, 0x89, 0x76, 0x54, 0x02, 0xFF, 0xFF, 0xFF,
    0xFF, 0xFF, 0xFF, 0x20, 0x45, 0x67, 0x98, 0xBA,
    WRITE_COMMAND_8, 0xFF,
    WRITE_BYTES, 5, 0x77, 0x01, 0x00, 0x00, 0x13,
    WRITE_C8_D8, 0xE5, 0xE4,
    WRITE_COMMAND_8, 0xFF,
    WRITE_BYTES, 5, 0x77, 0x01, 0x00, 0x00, 0x00,
    WRITE_C8_D8, 0x3A, 0x50,   // COLMOD = RGB565 (was 0x60 RGB666 in type9)
    WRITE_COMMAND_8, 0x11,
    END_WRITE,
    DELAY, 120,
    BEGIN_WRITE,
    WRITE_COMMAND_8, 0x29,
    END_WRITE
};

Arduino_DataBus *bus = new Arduino_XL9535SWSPI(
    IIC_SDA, IIC_SCL, -1, XL95X5_CS, XL95X5_SCLK, XL95X5_MOSI);
Arduino_ESP32RGBPanel *rgbpanel = new Arduino_ESP32RGBPanel(
    -1, 40, 39, 41,
    1, 2, 3, 4, 5,
    6, 7, 8, 9, 10, 11,
    12, 13, 42, 46, 45,
    1, 20, 2, 0,
    1, 30, 8, 1,
    10, 6'000'000L, false, 0, 0);   // LilyGo's exact params
Arduino_RGB_Display *gfx = new Arduino_RGB_Display(
    LCD_WIDTH, LCD_HEIGHT, rgbpanel, 0, true,
    bus, -1, st7701_rgb565_init, sizeof(st7701_rgb565_init));

// ───── LVGL display + draw buffer ─────
// 40 rows × 480 cols × 2 bytes = 38400 bytes per buffer in DRAM (fits easily)
static const uint32_t DRAW_BUF_ROWS = 40;
static lv_disp_draw_buf_t draw_buf;
static lv_color_t buf1[LCD_WIDTH * DRAW_BUF_ROWS];
static lv_color_t buf2[LCD_WIDTH * DRAW_BUF_ROWS];
static lv_disp_drv_t disp_drv;

static void my_disp_flush(lv_disp_drv_t *disp, const lv_area_t *area, lv_color_t *color_p) {
    uint32_t w = area->x2 - area->x1 + 1;
    uint32_t h = area->y2 - area->y1 + 1;
    gfx->draw16bitRGBBitmap(area->x1, area->y1, (uint16_t *)&color_p->full, w, h);
    lv_disp_flush_ready(disp);
}

void setup() {
    Serial.begin(115200);
    delay(3000);
    Serial.println("[lvgl_test] start");

    pinMode(LCD_BL, OUTPUT);
    digitalWrite(LCD_BL, HIGH);

    Wire.begin(IIC_SDA, IIC_SCL, 400000);

    // XL9535 workaround: lib only inits port 0, we need port 1 too.
    auto xl_w = [](uint8_t reg, uint8_t val) {
        Wire.beginTransmission(0x20);
        Wire.write(reg); Wire.write(val);
        Wire.endTransmission();
    };
    xl_w(0x06, 0x00); xl_w(0x07, 0x00);
    xl_w(0x02, 0xFF); xl_w(0x03, 0xFF);
    delay(10);
    xl_w(0x02, 0xFF & ~(1 << 5));   // LCD_RST low
    delay(50);
    xl_w(0x02, 0xFF);               // LCD_RST high
    delay(200);
    Serial.println("[lvgl_test] XL9535 ready, LCD_RST pulsed");

    gfx->begin();
    gfx->fillScreen(0x0000);
    Serial.println("[lvgl_test] gfx->begin done, screen cleared to black");

    // ───── LVGL init ─────
    lv_init();
    lv_disp_draw_buf_init(&draw_buf, buf1, buf2, LCD_WIDTH * DRAW_BUF_ROWS);
    lv_disp_drv_init(&disp_drv);
    disp_drv.hor_res = LCD_WIDTH;
    disp_drv.ver_res = LCD_HEIGHT;
    disp_drv.flush_cb = my_disp_flush;
    disp_drv.draw_buf = &draw_buf;
    lv_disp_drv_register(&disp_drv);
    Serial.println("[lvgl_test] LVGL display registered");

    // ───── Hello world: a single big centered label ─────
    lv_obj_t *scr = lv_scr_act();
    lv_obj_set_style_bg_color(scr, lv_color_white(), LV_PART_MAIN);
    lv_obj_t *label = lv_label_create(scr);
    lv_label_set_text(label, "Hello LVGL\nT-Panel DCP");
    lv_obj_set_style_text_color(label, lv_color_black(), LV_PART_MAIN);
    lv_obj_set_style_text_font(label, &lv_font_montserrat_14, LV_PART_MAIN);
    lv_obj_set_style_text_align(label, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN);
    lv_obj_center(label);
    Serial.println("[lvgl_test] label created, entering loop");
}

void loop() {
    lv_timer_handler();
    delay(5);
}
