#include "carto/carto.h"
#include "carto/raster.h"
#include "carto/geom.h"
#include "mvt.h"
#include <math.h>

struct carto_ctx {
    carto_arena *arena;
    carto_framebuffer *fb;
    const carto_style *style;
    int zoom;
    double tile_px;
    double origin_x, origin_y;
    carto_ipt *scratch;
    int scratch_cap;
};

carto_ctx *carto_begin(carto_arena *arena, carto_framebuffer *fb,
                       carto_viewport *vp, const carto_style *style) {
    if (!arena || !fb || !vp || !style) return NULL;

    carto_ctx *c = (carto_ctx *)carto_arena_alloc(arena, sizeof(carto_ctx), 8);
    if (!c) return NULL;

    c->arena = arena;
    c->fb = fb;
    c->style = style;
    c->zoom = vp->zoom;
    c->tile_px = (vp->tile_px > 0) ? (double)vp->tile_px : 256.0;

    double n = ldexp(1.0, vp->zoom);
    double world = n * c->tile_px;
    c->origin_x = carto_lon_to_norm(vp->lon) * world - fb->width / 2.0;
    c->origin_y = carto_lat_to_norm(vp->lat) * world - fb->height / 2.0;

    c->scratch_cap = 1 << 16;
    c->scratch = (carto_ipt *)carto_arena_alloc(arena,
        (size_t)c->scratch_cap * sizeof(carto_ipt), 4);
    if (!c->scratch) return NULL;

    vp->scale = carto_fix_from_float((float)(c->tile_px / (double)CARTO_TILE_EXTENT));
    vp->origin_x = carto_fix_from_float((float)c->origin_x);
    vp->origin_y = carto_fix_from_float((float)c->origin_y);

    carto_fb_clear(fb, carto_rgb565(style->bg));
    return c;
}

int carto_render_tile(carto_ctx *ctx, const uint8_t *mvt, size_t len,
                      int tile_x, int tile_y, int tile_z) {
    (void)tile_z;
    if (!ctx || !mvt || len == 0) return -1;

    double ox = (double)tile_x * ctx->tile_px - ctx->origin_x;
    double oy = (double)tile_y * ctx->tile_px - ctx->origin_y;

    static const carto_layer_kind order[5] = {
        CARTO_LAYER_WATER, CARTO_LAYER_LANDUSE, CARTO_LAYER_BUILDING,
        CARTO_LAYER_ROAD, CARTO_LAYER_PLACE
    };
    for (int i = 0; i < 5; ++i) {
        carto_mvt_render_category(ctx->fb, ctx->style, mvt, len, order[i],
                                  ox, oy, ctx->tile_px, ctx->scratch, ctx->scratch_cap);
    }
    return 0;
}

int carto_render_overlay(carto_ctx *ctx, const carto_overlay_point *pts, int n) {
    if (!ctx || !pts) return -1;
    double world = ldexp(1.0, ctx->zoom) * ctx->tile_px;
    for (int i = 0; i < n; ++i) {
        int x = (int)(carto_lon_to_norm(pts[i].lon) * world - ctx->origin_x);
        int y = (int)(carto_lat_to_norm(pts[i].lat) * world - ctx->origin_y);
        carto_rgb col = ctx->style->aircraft_color;
        if (pts[i].flags & CARTO_PT_EMERGENCY) col = ctx->style->aircraft_emergency_color;
        else if (pts[i].flags & CARTO_PT_SELECTED) col = ctx->style->aircraft_selected_color;
        carto_fill_triangle(ctx->fb, x, y - 8, x - 7, y + 8, x + 7, y + 8, col);
    }
    return 0;
}

void carto_end(carto_ctx *ctx) {
    (void)ctx;
}
