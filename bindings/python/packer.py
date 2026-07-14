import struct


def rgb565_to_rgb(v):
    r = ((v >> 11) & 0x1F) * 255 // 31
    g = ((v >> 5) & 0x3F) * 255 // 63
    b = (v & 0x1F) * 255 // 31
    return r, g, b


def _px(rgb565, w, h, fx, fy):
    if fx < 0: fx = 0
    if fy < 0: fy = 0
    if fx >= w: fx = w - 1
    if fy >= h: fy = h - 1
    i = (fy * w + fx) * 2
    return rgb565_to_rgb(rgb565[i] | (rgb565[i + 1] << 8))


def to_ansi_halfblock(rgb565, w, h, cols, rows):
    sh = rows * 2
    lines = []
    for cy in range(rows):
        parts = []
        prev = None
        for cx in range(cols):
            fx = cx * w // cols
            ur, ug, ub = _px(rgb565, w, h, fx, (2 * cy) * h // sh)
            lr, lg, lb = _px(rgb565, w, h, fx, (2 * cy + 1) * h // sh)
            cur = (ur, ug, ub, lr, lg, lb)
            if cur != prev:
                parts.append(f"\x1b[38;2;{ur};{ug};{ub};48;2;{lr};{lg};{lb}m")
                prev = cur
            parts.append("▀")
        parts.append("\x1b[0m")
        lines.append("".join(parts))
    return "\n".join(lines)


def to_bmp(rgb565, w, h, path):
    row_bytes = w * 3
    pad = (4 - (row_bytes & 3)) & 3
    stride = row_bytes + pad
    data_size = stride * h
    with open(path, "wb") as f:
        f.write(b"BM")
        f.write(struct.pack("<IHHI", 54 + data_size, 0, 0, 54))
        f.write(struct.pack("<IiiHHIIiiII", 40, w, h, 1, 24, 0, data_size, 0, 0, 0, 0))
        pad_bytes = b"\x00" * pad
        for y in range(h - 1, -1, -1):
            row = bytearray()
            base = y * w * 2
            for x in range(w):
                i = base + x * 2
                r, g, b = rgb565_to_rgb(rgb565[i] | (rgb565[i + 1] << 8))
                row += bytes((b, g, r))
            f.write(row)
            f.write(pad_bytes)
