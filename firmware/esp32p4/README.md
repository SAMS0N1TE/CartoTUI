# cartomap — ESP32-P4 firmware (first light)

Renders libcarto onto the **Waveshare ESP32-P4-WIFI6-Touch-LCD-4B** (4″
720×720 MIPI-DSI, GT911 touch, 32 MB PSRAM).

This is milestone **M1 — first light**: bring up the panel, render a test
scene with the shared `libcarto` core into an RGB565 framebuffer in PSRAM,
and push it to the display. It draws the same scene as the desktop
`render_to_bmp` harness, so a correct flash shows that image on the screen.

## What drives the screen

The DSI panel + GT911 touch + backlight are handled by the **official
Waveshare BSP** managed component, declared in `main/idf_component.yml`:

```
waveshare/esp32_p4_wifi6_touch_lcd_4b
```

So there is no hand-rolled or guessed panel init. `app_main.c` only:
1. `bsp_display_new()` — brings up the 2-lane DSI panel (480 Mbps) + IO
2. `bsp_display_brightness_init()` / `bsp_display_backlight_on()` — GPIO26 backlight
3. allocates a 720×720 RGB565 framebuffer in PSRAM (`MALLOC_CAP_SPIRAM`)
4. `carto_*` renders into it
5. `esp_lcd_panel_draw_bitmap()` — pushes the frame to the panel

## Board facts (Waveshare ESP32-P4-WIFI6-Touch-LCD-4B)

| Item | Value |
|---|---|
| Display | 4″ IPS 720×720, MIPI-DSI, D-PHY v1.1, 2-lane × 1.5 Gbps |
| DSI lane bit rate | 480 Mbps (per-lane) |
| LCD reset | GPIO27 |
| Backlight | GPIO26 (LEDC, output-inverted) |
| Touch | GT911, I²C SCL GPIO8 / SDA GPIO7 |
| PSRAM / flash | 32 MB / 32 MB |
| SD | SDIO 3.0 TF slot |

## Build & flash

Needs ESP-IDF 5.4.x (you have 5.4.3). From an IDF-exported shell:

```
cd firmware/esp32p4
idf.py set-target esp32p4
idf.py build
idf.py -p <COMx> flash monitor
```

The component manager downloads the Waveshare BSP on first build.

## Verify-on-hardware notes

I cannot cross-compile or flash P4 firmware from the dev box, so the
following are the integration points to confirm against your installed BSP
version when you build:

- **BSP API names.** `bsp_display_new` / `bsp_display_config_t.dsi_bus` /
  `bsp_display_brightness_init` / `bsp_display_backlight_on` follow the
  esp-bsp convention. If the Waveshare BSP version exposes slightly
  different names, adjust the four calls in `app_main.c`.
- **Framebuffer push.** `esp_lcd_panel_draw_bitmap` copies our PSRAM buffer
  to the panel. For higher frame rates later we can switch to the DPI
  panel's internal framebuffer via `esp_lcd_dpi_panel_get_frame_buffer`.

## Next milestones

- **M2** — load a baked `.carto` tile from the SD card, render a real map.
- **M3** — GT911 touch: drag-to-pan, pinch-zoom, re-render on change.
- **M4** — ADS-B overlay: feed LakeShark `adsb_aircraft_t` lat/lon as a
  dynamic layer over the basemap.
