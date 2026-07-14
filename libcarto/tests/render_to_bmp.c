#include "carto/carto.h"
#include "carto/raster.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void put_u16(uint8_t *p, uint16_t v) {
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8);
}

static void put_u32(uint8_t *p, uint32_t v) {
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8);
    p[2] = (uint8_t)(v >> 16);
    p[3] = (uint8_t)(v >> 24);
}

static int write_bmp(const char *path, const carto_framebuffer *fb) {
    int w = fb->width;
    int h = fb->height;
    int row_bytes = w * 3;
    int pad = (4 - (row_bytes & 3)) & 3;
    int stride = row_bytes + pad;
    uint32_t data_size = (uint32_t)stride * (uint32_t)h;
    uint32_t file_size = 54u + data_size;

    FILE *f = fopen(path, "wb");
    if (!f) return -1;

    uint8_t hdr[54];
    memset(hdr, 0, sizeof(hdr));
    hdr[0] = 'B';
    hdr[1] = 'M';
    put_u32(hdr + 2, file_size);
    put_u32(hdr + 10, 54);
    put_u32(hdr + 14, 40);
    put_u32(hdr + 18, (uint32_t)w);
    put_u32(hdr + 22, (uint32_t)h);
    put_u16(hdr + 26, 1);
    put_u16(hdr + 28, 24);
    put_u32(hdr + 34, data_size);
    fwrite(hdr, 1, 54, f);

    uint8_t *line = (uint8_t *)malloc((size_t)stride);
    if (!line) { fclose(f); return -1; }
    memset(line, 0, (size_t)stride);

    for (int y = h - 1; y >= 0; --y) {
        const uint16_t *src = (const uint16_t *)(fb->pixels + (size_t)y * fb->stride);
        for (int x = 0; x < w; ++x) {
            uint16_t p = src[x];
            uint8_t r = (uint8_t)((((p >> 11) & 0x1F) * 255) / 31);
            uint8_t g = (uint8_t)((((p >> 5) & 0x3F) * 255) / 63);
            uint8_t b = (uint8_t)(((p & 0x1F) * 255) / 31);
            line[x * 3 + 0] = b;
            line[x * 3 + 1] = g;
            line[x * 3 + 2] = r;
        }
        fwrite(line, 1, (size_t)stride, f);
    }

    free(line);
    fclose(f);
    return 0;
}

int main(int argc, char **argv) {
    const char *out = argc > 1 ? argv[1] : "carto_test.bmp";
    const int W = 400;
    const int H = 240;

    uint8_t *pixels = (uint8_t *)malloc((size_t)W * (size_t)H * 2);
    if (!pixels) return 1;

    carto_framebuffer fb;
    if (carto_fb_init(&fb, W, H, CARTO_FMT_RGB565, pixels) != 0) {
        free(pixels);
        return 1;
    }

    carto_style s;
    carto_style_default(&s);

    carto_fb_clear(&fb, carto_rgb565(s.bg));

    carto_fill_rect(&fb, 0, 0, 150, 110, s.water);
    carto_fill_rect(&fb, 250, 150, 150, 90, s.park);
    for (int i = 0; i < 4; ++i)
        carto_fill_rect(&fb, 180 + i * 30, 40, 20, 20, s.building);

    carto_draw_line(&fb, 0, 120, 399, 120, s.road_width[10], s.road_color_by_prio[10]);
    carto_draw_line(&fb, 200, 0, 200, 239, s.road_width[8], s.road_color_by_prio[8]);
    carto_draw_line(&fb, 60, 0, 60, 239, s.road_width[4], s.road_color_by_prio[4]);
    carto_draw_line(&fb, 0, 190, 399, 190, s.road_width[6], s.road_color_by_prio[6]);
    carto_draw_line(&fb, 0, 60, 250, 200, s.road_width[2], s.road_color_by_prio[2]);

    carto_fill_triangle(&fb, 120, 70, 112, 88, 128, 88, s.aircraft_color);
    carto_fill_triangle(&fb, 300, 120, 292, 138, 308, 138, s.aircraft_selected_color);
    carto_fill_triangle(&fb, 330, 60, 322, 78, 338, 78, s.aircraft_emergency_color);

    int rc = write_bmp(out, &fb);
    if (rc == 0) printf("wrote %s (%dx%d RGB565)\n", out, W, H);
    else fprintf(stderr, "failed writing %s\n", out);

    free(pixels);
    return rc;
}
