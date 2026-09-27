#ifndef CARTO_TERMINAL_H
#define CARTO_TERMINAL_H
#include <stdint.h>
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif

typedef struct { uint32_t glyph, fg, bg; } carto_terminal_cell;

/* depth is 8 (xterm fixed 256-color palette) or 24 (RGB).
 * UINT32_MAX denotes the terminal's default foreground/background.
 * Glyphs must be printable, one-column Unicode code points. */
void carto_prepare_terminal(const uint32_t *glyph, const uint32_t *fg,
                           const uint32_t *bg, carto_terminal_cell *dst,
                           size_t n, unsigned depth);

/* Returns bytes written, or SIZE_MAX for insufficient capacity/invalid depth.
 * Do not transmit partial output on failure. Pass prev=NULL after resize,
 * exposure, terminal reset, palette changes, or any unknown screen damage.
 * visible may be NULL; otherwise zero entries protect floating windows. */
size_t carto_encode_terminal(const carto_terminal_cell *now,
                            const carto_terminal_cell *prev, const uint8_t *visible,
                            unsigned cols, unsigned rows, unsigned xoff, unsigned yoff,
                            char *out, size_t capacity, unsigned depth);

void carto_expand_rgb565(const uint16_t *src, const uint32_t *lut,
                        uint8_t *dst, size_t n);
void carto_luminance_rgb(const uint8_t *src, float *dst, size_t n);
void carto_blend_rgb(const uint8_t *base, const uint8_t *overlay,
                     const float *alpha, uint8_t *dst, size_t n);
void carto_braille_colors(const uint8_t *rgb, const uint8_t *lit,
                          unsigned cols, unsigned rows, uint32_t *dst);
#ifdef __cplusplus
}
#endif
#endif
