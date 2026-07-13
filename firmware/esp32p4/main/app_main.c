#include "carto/carto.h"
#include "carto/raster.h"

#include "bsp/esp-bsp.h"
#include "esp_lcd_panel_ops.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define MAP_W 720
#define MAP_H 720

static const char *TAG = "cartomap";

static void draw_test_scene(carto_framebuffer *fb, const carto_style *s) {
    carto_fb_clear(fb, carto_rgb565(s->bg));

    carto_fill_rect(fb, 0, 0, 280, 200, s->water);
    carto_fill_rect(fb, 440, 470, 280, 250, s->park);
    for (int i = 0; i < 5; ++i)
        carto_fill_rect(fb, 320 + i * 48, 90, 36, 36, s->building);

    carto_draw_line(fb, 0, 360, 719, 360, s->road_width[10] * 2, s->road_color_by_prio[10]);
    carto_draw_line(fb, 360, 0, 360, 719, s->road_width[8] * 2, s->road_color_by_prio[8]);
    carto_draw_line(fb, 120, 0, 120, 719, s->road_width[4] * 2, s->road_color_by_prio[4]);
    carto_draw_line(fb, 0, 560, 719, 560, s->road_width[6] * 2, s->road_color_by_prio[6]);
    carto_draw_line(fb, 0, 120, 470, 620, s->road_width[2] * 2, s->road_color_by_prio[2]);

    carto_fill_triangle(fb, 360, 200, 344, 236, 376, 236, s->aircraft_color);
    carto_fill_triangle(fb, 540, 360, 524, 396, 556, 396, s->aircraft_selected_color);
    carto_fill_triangle(fb, 600, 110, 584, 146, 616, 146, s->aircraft_emergency_color);
}

void app_main(void) {
    bsp_display_config_t disp_cfg = {0};

    esp_lcd_panel_handle_t panel = NULL;
    esp_lcd_panel_io_handle_t io = NULL;
    ESP_ERROR_CHECK(bsp_display_new(&disp_cfg, &panel, &io));
    ESP_ERROR_CHECK(esp_lcd_panel_disp_on_off(panel, true));
    bsp_display_brightness_init();
    bsp_display_backlight_on();

    size_t fb_bytes = (size_t)MAP_W * (size_t)MAP_H * 2;
    uint8_t *pixels = heap_caps_malloc(fb_bytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!pixels) {
        ESP_LOGE(TAG, "failed to allocate %u byte framebuffer in PSRAM", (unsigned)fb_bytes);
        return;
    }

    carto_framebuffer fb;
    carto_fb_init(&fb, MAP_W, MAP_H, CARTO_FMT_RGB565, pixels);

    carto_style style;
    carto_style_default(&style);

    draw_test_scene(&fb, &style);

    ESP_ERROR_CHECK(esp_lcd_panel_draw_bitmap(panel, 0, 0, MAP_W, MAP_H, pixels));
    ESP_LOGI(TAG, "libcarto first light: %dx%d RGB565 pushed to panel", MAP_W, MAP_H);

    while (1) {
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}
