#include "carto/raster.h"

uint16_t carto_rgb565(carto_rgb c) {
    return (uint16_t)(((c.r & 0xF8) << 8) | ((c.g & 0xFC) << 3) | (c.b >> 3));
}

void carto_put_px(carto_framebuffer *fb, int x, int y, carto_rgb c) {
    if (!fb || x < 0 || y < 0 || x >= fb->width || y >= fb->height) return;
    uint8_t *row = fb->pixels + (size_t)y * fb->stride;
    switch (fb->format) {
        case CARTO_FMT_RGB565:
            ((uint16_t *)row)[x] = carto_rgb565(c);
            return;
        case CARTO_FMT_RGBA8888: {
            uint8_t *p = row + (size_t)x * 4;
            p[0] = c.r; p[1] = c.g; p[2] = c.b; p[3] = 0xFF;
            return;
        }
        case CARTO_FMT_INDEXED8:
            row[x] = (uint8_t)((c.r * 30 + c.g * 59 + c.b * 11) / 100);
            return;
        case CARTO_FMT_MONO1: {
            int lum = (c.r * 30 + c.g * 59 + c.b * 11) / 100;
            uint8_t mask = (uint8_t)(0x80 >> (x & 7));
            if (lum >= 128) row[x >> 3] |= mask;
            else            row[x >> 3] &= (uint8_t)~mask;
            return;
        }
    }
}

void carto_fill_rect(carto_framebuffer *fb, int x, int y, int w, int h, carto_rgb c) {
    if (!fb) return;
    int x0 = x < 0 ? 0 : x;
    int y0 = y < 0 ? 0 : y;
    int x1 = x + w; if (x1 > fb->width)  x1 = fb->width;
    int y1 = y + h; if (y1 > fb->height) y1 = fb->height;
    for (int yy = y0; yy < y1; ++yy)
        for (int xx = x0; xx < x1; ++xx)
            carto_put_px(fb, xx, yy, c);
}

void carto_draw_line(carto_framebuffer *fb, int x0, int y0, int x1, int y1,
                     int width, carto_rgb c) {
    if (!fb) return;
    if (width < 1) width = 1;
    int half = width / 2;

    int dx = x1 - x0; if (dx < 0) dx = -dx;
    int dy = y1 - y0; if (dy < 0) dy = -dy;
    int sx = x0 < x1 ? 1 : -1;
    int sy = y0 < y1 ? 1 : -1;
    int err = dx - dy;

    for (;;) {
        if (width == 1) carto_put_px(fb, x0, y0, c);
        else            carto_fill_rect(fb, x0 - half, y0 - half, width, width, c);
        if (x0 == x1 && y0 == y1) break;
        int e2 = err << 1;
        if (e2 > -dy) { err -= dy; x0 += sx; }
        if (e2 <  dx) { err += dx; y0 += sy; }
    }
}

static int carto_edge(int ax, int ay, int bx, int by, int px, int py) {
    return (bx - ax) * (py - ay) - (by - ay) * (px - ax);
}

void carto_fill_triangle(carto_framebuffer *fb, int x0, int y0, int x1, int y1,
                         int x2, int y2, carto_rgb c) {
    if (!fb) return;
    int minx = x0; if (x1 < minx) minx = x1; if (x2 < minx) minx = x2;
    int miny = y0; if (y1 < miny) miny = y1; if (y2 < miny) miny = y2;
    int maxx = x0; if (x1 > maxx) maxx = x1; if (x2 > maxx) maxx = x2;
    int maxy = y0; if (y1 > maxy) maxy = y1; if (y2 > maxy) maxy = y2;
    if (minx < 0) minx = 0;
    if (miny < 0) miny = 0;
    if (maxx >= fb->width)  maxx = fb->width - 1;
    if (maxy >= fb->height) maxy = fb->height - 1;

    int area = carto_edge(x0, y0, x1, y1, x2, y2);
    if (area == 0) return;

    for (int py = miny; py <= maxy; ++py) {
        for (int px = minx; px <= maxx; ++px) {
            int w0 = carto_edge(x1, y1, x2, y2, px, py);
            int w1 = carto_edge(x2, y2, x0, y0, px, py);
            int w2 = carto_edge(x0, y0, x1, y1, px, py);
            int inside = area > 0
                ? (w0 >= 0 && w1 >= 0 && w2 >= 0)
                : (w0 <= 0 && w1 <= 0 && w2 <= 0);
            if (inside) carto_put_px(fb, px, py, c);
        }
    }
}
