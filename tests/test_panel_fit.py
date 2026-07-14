from cartotui.ui.widgets.panel import Panel


def _len(line):
    return sum(len(t) for _, t in line)


def test_short_line_is_padded_to_inner():
    line = [("class:panel.value", "Compass")]
    fitted = Panel._fit_line(line, 20)
    assert _len(fitted) == 20
    assert fitted[0] == ("class:panel.value", "Compass")


def test_exact_line_unchanged():
    line = [("s", "abcde")]
    assert Panel._fit_line(line, 5) == [("s", "abcde")]


def test_long_line_is_clipped():
    line = [("s", "abc"), ("t", "defghijk")]
    fitted = Panel._fit_line(line, 5)
    assert _len(fitted) == 5
    assert fitted[0] == ("s", "abc")
    assert fitted[1] == ("t", "de")


def test_multi_run_short_pads_once():
    line = [("a", "hi"), ("b", "yo")]
    fitted = Panel._fit_line(line, 10)
    assert _len(fitted) == 10
    assert fitted[-1][1].strip() == ""
