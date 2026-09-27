from prompt_toolkit.output import ColorDepth

from cartotui.ui.direct_paint import paint_rows

ROWS = [[("fg:#20386a bg:#202429", "▀▀")], [("fg:#ff5052 bg:#000000", "▀▀")]]


def test_resets_inherited_reverse_and_bold_before_pixels():
    stream = paint_rows(ROWS, 0, 0, 2, 2, [])
    assert stream.startswith("\x1b7\x1b[0m")
    assert stream.endswith("\x1b[0m\x1b8")


def test_ssh_palette_depth_is_honoured():
    stream = paint_rows(ROWS, 0, 0, 2, 2, [], color_depth=ColorDepth.DEPTH_8_BIT)
    assert "38;5;" in stream and "48;5;" in stream
    assert "38;2;" not in stream and "48;2;" not in stream


def test_idle_frame_sends_nothing_and_changed_row_only():
    assert paint_rows(ROWS, 0, 0, 2, 2, [], previous_rows=ROWS) == ""
    changed = [ROWS[0], [("fg:#ff0000 bg:#000000", "▀▀")]]
    stream = paint_rows(changed, 0, 0, 2, 2, [], previous_rows=ROWS)
    assert "\x1b[2;1H" in stream
    assert "\x1b[1;1H" not in stream


def test_overlay_is_not_overwritten():
    stream = paint_rows(ROWS, 0, 0, 2, 2, [(0, 0, 2, 1)])
    assert "\x1b[1;1H" not in stream
    assert "\x1b[2;1H" in stream


def test_quantized_equal_colours_do_not_resend_attributes():
    rows = [[("fg:#101010 bg:#000000", "a"), ("fg:#111111 bg:#010101", "b")]]
    stream = paint_rows(rows, 0, 0, 2, 1, [], color_depth=ColorDepth.DEPTH_8_BIT)
    assert stream.count("38;5;") == 1
    assert stream.count("48;5;") == 1


def test_16_colour_pixels_do_not_get_text_contrast_correction():
    rows = [[("fg:#101010 bg:#111111", "▀")]]
    stream = paint_rows(rows, 0, 0, 1, 1, [], color_depth=ColorDepth.DEPTH_4_BIT)
    assert "\x1b[30m" in stream
    assert "\x1b[40m" in stream
    assert "38;2;" not in stream
