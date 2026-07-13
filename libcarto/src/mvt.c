#include "mvt.h"

typedef struct {
    carto_framebuffer *fb;
    const carto_style *style;
    double ox, oy, tile_px, per_ext;
    carto_layer_kind category;
    carto_ipt *scratch;
    int scratch_cap;
} mvt_ctx;

static uint64_t rvarint(const uint8_t *b, size_t len, size_t *pos) {
    uint64_t r = 0;
    int s = 0;
    while (*pos < len) {
        uint8_t c = b[(*pos)++];
        r |= (uint64_t)(c & 0x7f) << s;
        if (!(c & 0x80)) break;
        s += 7;
        if (s > 63) break;
    }
    return r;
}

static int32_t zigzag(uint32_t n) {
    return (int32_t)((n >> 1) ^ (0u - (n & 1)));
}

static void category_colors(const mvt_ctx *m, carto_rgb *fill, carto_rgb *line,
                            carto_rgb *pt, int *lw) {
    *lw = 1;
    switch (m->category) {
        case CARTO_LAYER_WATER:    *fill = *line = *pt = m->style->water; break;
        case CARTO_LAYER_LANDUSE:  *fill = *line = *pt = m->style->park; break;
        case CARTO_LAYER_BUILDING: *fill = *line = *pt = m->style->building; break;
        case CARTO_LAYER_ROAD:     *fill = *line = *pt = m->style->road_color_by_prio[7]; break;
        default:                   *fill = *line = *pt = m->style->label_color; break;
    }
}

static void render_feature(mvt_ctx *m, const uint8_t *g, size_t glen, int geomtype) {
    carto_rgb fillc, linec, ptc;
    int lw;
    category_colors(m, &fillc, &linec, &ptc, &lw);

    size_t p = 0;
    int cx = 0, cy = 0, n = 0;
    carto_ipt *pts = m->scratch;

    while (p < glen) {
        uint64_t cmdint = rvarint(g, glen, &p);
        uint32_t id = (uint32_t)(cmdint & 7);
        uint32_t count = (uint32_t)(cmdint >> 3);

        if (id == 1) {
            if (geomtype == 2 && n >= 2) carto_polyline(m->fb, pts, n, lw, linec);
            n = 0;
            for (uint32_t k = 0; k < count; ++k) {
                cx += zigzag((uint32_t)rvarint(g, glen, &p));
                cy += zigzag((uint32_t)rvarint(g, glen, &p));
                int fx = (int)(m->ox + cx * m->per_ext);
                int fy = (int)(m->oy + cy * m->per_ext);
                if (geomtype == 1) {
                    carto_fill_rect(m->fb, fx - 1, fy - 1, 3, 3, ptc);
                } else if (n < m->scratch_cap) {
                    pts[n].x = fx; pts[n].y = fy; ++n;
                }
            }
        } else if (id == 2) {
            for (uint32_t k = 0; k < count; ++k) {
                cx += zigzag((uint32_t)rvarint(g, glen, &p));
                cy += zigzag((uint32_t)rvarint(g, glen, &p));
                if (n < m->scratch_cap) {
                    pts[n].x = (int)(m->ox + cx * m->per_ext);
                    pts[n].y = (int)(m->oy + cy * m->per_ext);
                    ++n;
                }
            }
        } else if (id == 7) {
            if (geomtype == 3 && n >= 3) carto_fill_polygon(m->fb, pts, n, fillc);
            n = 0;
        }
    }
    if (geomtype == 2 && n >= 2) carto_polyline(m->fb, pts, n, lw, linec);
}

static void render_feature_msg(mvt_ctx *m, const uint8_t *b, size_t len) {
    int geomtype = 0;
    const uint8_t *geom = NULL;
    size_t geomlen = 0, p = 0;
    while (p < len) {
        uint64_t key = rvarint(b, len, &p);
        uint32_t fn = (uint32_t)(key >> 3), wt = (uint32_t)(key & 7);
        if (wt == 0) {
            uint64_t v = rvarint(b, len, &p);
            if (fn == 3) geomtype = (int)v;
        } else if (wt == 2) {
            uint64_t l = rvarint(b, len, &p);
            if (fn == 4) { geom = b + p; geomlen = (size_t)l; }
            p += (size_t)l;
        } else if (wt == 5) { p += 4; }
        else if (wt == 1) { p += 8; }
        else break;
    }
    if (geom) render_feature(m, geom, geomlen, geomtype);
}

static void render_layer(mvt_ctx *m, const uint8_t *b, size_t len) {
    char name[80];
    int extent = 4096;
    size_t p = 0;
    name[0] = 0;
    while (p < len) {
        uint64_t key = rvarint(b, len, &p);
        uint32_t fn = (uint32_t)(key >> 3), wt = (uint32_t)(key & 7);
        if (wt == 2) {
            uint64_t l = rvarint(b, len, &p);
            if (fn == 1) {
                int cn = (int)l; if (cn > 79) cn = 79;
                for (int i = 0; i < cn; ++i) name[i] = (char)b[p + i];
                name[cn] = 0;
            }
            p += (size_t)l;
        } else if (wt == 0) {
            uint64_t v = rvarint(b, len, &p);
            if (fn == 5) extent = (int)v;
        } else if (wt == 5) { p += 4; }
        else if (wt == 1) { p += 8; }
        else break;
    }

    if (carto_classify_layer(name) != m->category) return;
    m->per_ext = m->tile_px / (double)(extent > 0 ? extent : 4096);

    p = 0;
    while (p < len) {
        uint64_t key = rvarint(b, len, &p);
        uint32_t fn = (uint32_t)(key >> 3), wt = (uint32_t)(key & 7);
        if (wt == 2) {
            uint64_t l = rvarint(b, len, &p);
            if (fn == 2) render_feature_msg(m, b + p, (size_t)l);
            p += (size_t)l;
        } else if (wt == 0) { rvarint(b, len, &p); }
        else if (wt == 5) { p += 4; }
        else if (wt == 1) { p += 8; }
        else break;
    }
}

void carto_mvt_render_category(carto_framebuffer *fb, const carto_style *style,
                              const uint8_t *tile, size_t len,
                              carto_layer_kind category,
                              double ox, double oy, double tile_px,
                              carto_ipt *scratch, int scratch_cap) {
    mvt_ctx m;
    m.fb = fb;
    m.style = style;
    m.ox = ox;
    m.oy = oy;
    m.tile_px = tile_px;
    m.per_ext = tile_px / 4096.0;
    m.category = category;
    m.scratch = scratch;
    m.scratch_cap = scratch_cap;

    size_t p = 0;
    while (p < len) {
        uint64_t key = rvarint(tile, len, &p);
        uint32_t fn = (uint32_t)(key >> 3), wt = (uint32_t)(key & 7);
        if (wt == 2) {
            uint64_t l = rvarint(tile, len, &p);
            if (fn == 3) render_layer(&m, tile + p, (size_t)l);
            p += (size_t)l;
        } else if (wt == 0) { rvarint(tile, len, &p); }
        else if (wt == 5) { p += 4; }
        else if (wt == 1) { p += 8; }
        else break;
    }
}
