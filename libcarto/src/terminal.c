/* Portable packed terminal encoder. No CPU-specific ISA requirement. */
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include "carto/terminal.h"

/* LUT words use little-endian RGBA channel packing, independent of host byte order. */
void carto_expand_rgb565(const uint16_t *src, const uint32_t *lut, uint8_t *dst, size_t n) {
    for(size_t i=0;i<n;i++) {
        uint32_t color=lut[src[i]];
        dst[3*i]=(uint8_t)color;
        dst[3*i+1]=(uint8_t)(color>>8);
        dst[3*i+2]=(uint8_t)(color>>16);
    }
}

void carto_luminance_rgb(const uint8_t *src, float *dst, size_t n) {
    for(size_t i=0;i<n;i++)
        dst[i]=(float)(0.299*src[3*i]+0.587*src[3*i+1]+0.114*src[3*i+2])/255.0f;
}

void carto_blend_rgb(const uint8_t *base, const uint8_t *overlay,
                     const float *alpha, uint8_t *dst, size_t n) {
    for(size_t i=0;i<n;i++) {
        float a=alpha[i], inverse=1.0f-a;
        for(size_t k=0;k<3;k++) {
            /* Match NumPy's separate float32 operations, including on FMA CPUs. */
            volatile float left=(float)base[3*i+k]*inverse;
            volatile float right=(float)overlay[3*i+k]*a;
            float value=left+right;
            if(value<0.0f) value=0.0f;
            if(value>255.0f) value=255.0f;
            dst[3*i+k]=(uint8_t)value;
        }
    }
}

void carto_braille_colors(const uint8_t *rgb, const uint8_t *lit,
                          unsigned cols, unsigned rows, uint32_t *dst) {
    size_t w=(size_t)cols*2;
    for(unsigned y=0;y<rows;y++) for(unsigned x=0;x<cols;x++) {
        unsigned count=0, sum[3]={0,0,0}, whole[3]={0,0,0};
        for(unsigned dy=0;dy<4;dy++) for(unsigned dx=0;dx<2;dx++) {
            size_t i=((size_t)y*4+dy)*w+x*2+dx;
            count+=lit[i]!=0;
            for(unsigned k=0;k<3;k++) {
                whole[k]+=rgb[i*3+k];
                if(lit[i]) sum[k]+=rgb[i*3+k];
            }
        }
        float inverse=count?1.0f/(float)count:0.125f;
        unsigned r=(unsigned)((float)(count?sum[0]:whole[0])*inverse);
        unsigned g=(unsigned)((float)(count?sum[1]:whole[1])*inverse);
        unsigned b=(unsigned)((float)(count?sum[2]:whole[2])*inverse);
        dst[(size_t)y*cols+x]=(r<<16)|(g<<8)|b;
    }
}
typedef carto_terminal_cell cell;
#ifndef GAP_BRIDGE
#define GAP_BRIDGE 0
#endif
static const int cube[6] = {0, 95, 135, 175, 215, 255};
static int nearest(int v) {
    return v < 48 ? 0 : v <= 115 ? 1 : v <= 155 ? 2 : v <= 195 ? 3 : v <= 235 ? 4 : 5;
}
static uint32_t quant(uint32_t rgb) {
    int r=(rgb>>16)&255, g=(rgb>>8)&255, b=rgb&255;
    int ri=nearest(r), gi=nearest(g), bi=nearest(b);
    int gray=(r+g+b-24+14)/30;
    if(gray<0) gray=0;
    if(gray>23) gray=23;
    int v=8+10*gray;
    int rd=r-cube[ri], gd=g-cube[gi], bd=b-cube[bi];
    int rc=r-v, gc=g-v, bc=b-v;
    return rd*rd+gd*gd+bd*bd <= rc*rc+gc*gc+bc*bc ?
        (uint32_t)(16+36*ri+6*gi+bi) : (uint32_t)(232+gray);
}
void carto_prepare_terminal(const uint32_t *glyph, const uint32_t *fg, const uint32_t *bg,
                   cell *dst, size_t n, unsigned depth) {
    for(size_t i=0;i<n;i++) {
        dst[i].fg=(depth==8 && fg[i]!=UINT32_MAX) ? quant(fg[i]) : fg[i];
        dst[i].bg=(depth==8 && bg[i]!=UINT32_MAX) ? quant(bg[i]) : bg[i];
        dst[i].glyph=(glyph[i]==0x2580 && dst[i].fg==dst[i].bg) ? 32 : glyph[i];
    }
}
typedef struct { char *out; size_t used, cap; int failed; } writer;
static void put(writer *w, const char *s, size_t n) {
    if(w->failed || n>w->cap-w->used) { w->failed=1; return; }
    memcpy(w->out+w->used,s,n); w->used+=n;
}
static void number(writer *w, unsigned n) {
    char b[16]; unsigned k=0;
    do { b[k++]=(char)('0'+n%10); n/=10; } while(n);
    while(k) put(w,b+--k,1);
}
static void cursor(writer *w, unsigned x, unsigned y) {
    put(w,"\033[",2); number(w,y+1); put(w,";",1); number(w,x+1); put(w,"H",1);
}
static void color(writer *w, unsigned n, int bg, unsigned depth) {
    if(n==UINT32_MAX) { put(w,bg?"\033[49m":"\033[39m",5); return; }
    put(w,bg?"\033[48;":"\033[38;",5);
    if(depth==8) { put(w,"5;",2); number(w,n); }
    else { put(w,"2;",2); number(w,(n>>16)&255); put(w,";",1);
           number(w,(n>>8)&255); put(w,";",1); number(w,n&255); }
    put(w,"m",1);
}
static void glyph(writer *w, uint32_t c) {
    char b[4]; size_t n;
    if(c<128) { b[0]=(char)c;n=1; }
    else if(c<2048) { b[0]=(char)(192|(c>>6));b[1]=(char)(128|(c&63));n=2; }
    else if(c<65536) { b[0]=(char)(224|(c>>12));b[1]=(char)(128|((c>>6)&63));b[2]=(char)(128|(c&63));n=3; }
    else { b[0]=(char)(240|(c>>18));b[1]=(char)(128|((c>>12)&63));b[2]=(char)(128|((c>>6)&63));b[3]=(char)(128|(c&63));n=4; }
    put(w,b,n);
}
/* SIZE_MAX means insufficient capacity; the caller must not transmit it.
 * Previous cells must describe what was actually painted, including masks.
 * Layout/exposure changes require prev=NULL or explicit invalidation. */
size_t carto_encode_terminal(const cell *now, const cell *prev, const uint8_t *visible,
                    unsigned cols, unsigned rows, unsigned xoff, unsigned yoff,
                    char *out, size_t capacity, unsigned depth) {
    writer w={out,0,capacity,0}; uint32_t fg=0,bg=0; int started=0, colored=0;
    if(depth!=8 && depth!=24) return SIZE_MAX;
    for(unsigned y=0;y<rows;y++) {
        int adjacent=0;
        for(unsigned x=0;x<cols;x++) {
            size_t i=(size_t)y*cols+x; const cell *c=now+i;
            if(visible&&!visible[i]) { adjacent=0; continue; }
            if(prev&&!memcmp(c,prev+i,sizeof(cell))) {
                int bridge=0;
                /* Spending a few unchanged glyphs can cost less than CUP plus
                 * colour restoration. This remains an experimental heuristic. */
                if(adjacent) {
                    for(unsigned d=1; d<=GAP_BRIDGE && x+d<cols; d++) {
                        if(visible&&!visible[i+d]) break;
                        if(memcmp(now+i+d,prev+i+d,sizeof(cell))) { bridge=1;break; }
                    }
                }
                if(!bridge) { adjacent=0; continue; }
            }
            if(!started) { put(&w,"\0337\033[0m",6);started=1; }
            if(!adjacent) cursor(&w,x+xoff,y+yoff);
            if(!colored || c->fg!=fg) { color(&w,c->fg,0,depth);fg=c->fg; }
            if(!colored || c->bg!=bg) { color(&w,c->bg,1,depth);bg=c->bg; }
            colored=1;
            glyph(&w,c->glyph); adjacent=1;
        }
    }
    if(started) put(&w,"\033[0m\0338",6);
    return w.failed ? SIZE_MAX : w.used;
}

