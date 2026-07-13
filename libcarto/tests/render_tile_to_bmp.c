#include "carto/carto.h"
#include "carto/raster.h"
#include "carto/geom.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void put_u16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); }
static void put_u32(uint8_t *p, uint32_t v) {
    p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24);
}

static int write_bmp(const char *path, const carto_framebuffer *fb) {
    int w = fb->width, h = fb->height;
    int stride = w * 3 + ((4 - (w * 3 & 3)) & 3);
    uint32_t data_size = (uint32_t)stride * (uint32_t)h;
    FILE *f = fopen(path, "wb");
    if (!f) return -1;
    uint8_t hdr[54];
    memset(hdr, 0, sizeof(hdr));
    hdr[0] = 'B'; hdr[1] = 'M';
    put_u32(hdr + 2, 54u + data_size);
    put_u32(hdr + 10, 54);
    put_u32(hdr + 14, 40);
    put_u32(hdr + 18, (uint32_t)w);
    put_u32(hdr + 22, (uint32_t)h);
    put_u16(hdr + 26, 1);
    put_u16(hdr + 28, 24);
    put_u32(hdr + 34, data_size);
    fwrite(hdr, 1, 54, f);
    uint8_t *line = (uint8_t *)malloc((size_t)stride);
    memset(line, 0, (size_t)stride);
    for (int y = h - 1; y >= 0; --y) {
        const uint16_t *src = (const uint16_t *)(fb->pixels + (size_t)y * fb->stride);
        for (int x = 0; x < w; ++x) {
            uint16_t p = src[x];
            line[x * 3 + 0] = (uint8_t)(((p & 0x1F) * 255) / 31);
            line[x * 3 + 1] = (uint8_t)((((p >> 5) & 0x3F) * 255) / 63);
            line[x * 3 + 2] = (uint8_t)((((p >> 11) & 0x1F) * 255) / 31);
        }
        fwrite(line, 1, (size_t)stride, f);
    }
    free(line);
    fclose(f);
    return 0;
}

static uint8_t *read_file(const char *path, size_t *out_len) {
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    uint8_t *buf = (uint8_t *)malloc((size_t)n);
    if (buf) *out_len = fread(buf, 1, (size_t)n, f);
    fclose(f);
    return buf;
}

int main(int argc, char **argv) {
    const char *in = argc > 1 ? argv[1] : "fixtures/sample.mvt";
    const char *out = argc > 2 ? argv[2] : "tile.bmp";
    int z = argc > 3 ? atoi(argv[3]) : 14;
    int tx = argc > 4 ? atoi(argv[4]) : 4936;
    int ty = argc > 5 ? atoi(argv[5]) : 6007;
    const int W = 1024, H = 1024;

    size_t len = 0;
    uint8_t *tile = read_file(in, &len);
    if (!tile) { fprintf(stderr, "cannot read %s\n", in); return 1; }
    fprintf(stderr, "tile %s: %zu bytes, z%d %d/%d\n", in, len, z, tx, ty);

    uint8_t *pixels = (uint8_t *)malloc((size_t)W * H * 2);
    carto_framebuffer fb;
    carto_fb_init(&fb, W, H, CARTO_FMT_RGB565, pixels);

    size_t arena_sz = 8u * 1024 * 1024;
    uint8_t *arena_buf = (uint8_t *)malloc(arena_sz);
    carto_arena arena;
    carto_arena_init(&arena, arena_buf, arena_sz);

    carto_style style;
    carto_style_default(&style);

    double lat, lon;
    carto_tile_center(tx, ty, z, &lat, &lon);

    carto_viewport vp;
    memset(&vp, 0, sizeof(vp));
    vp.lat = lat; vp.lon = lon; vp.zoom = z; vp.fb_w = W; vp.fb_h = H; vp.tile_px = W;

    carto_ctx *ctx = carto_begin(&arena, &fb, &vp, &style);
    if (!ctx) { fprintf(stderr, "carto_begin failed\n"); return 1; }
    carto_render_tile(ctx, tile, len, tx, ty, z);
    carto_end(ctx);

    if (write_bmp(out, &fb) == 0)
        fprintf(stderr, "wrote %s (%dx%d), arena used %zu KB\n",
                out, W, H, carto_arena_used(&arena) / 1024);

    free(tile); free(pixels); free(arena_buf);
    return 0;
}
