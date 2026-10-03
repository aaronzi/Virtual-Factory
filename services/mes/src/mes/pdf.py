"""Minimal PDF 1.4 writer for one-page documents (no dependency): text in the standard fonts Helvetica and
Helvetica-Bold (WinAnsi encoding = cp1252, so the text stays searchable and the files stay small), lines and
filled rectangles. Coordinates in points, y measured from the top edge. Output is deterministic."""

from __future__ import annotations

A4 = (595.28, 841.89)
# characters outside cp1252 used in technical texts
SUBSTITUTES = {"≤": "<=", "≥": ">=", "Δ": "Delta ", "∆": "Delta ", "·": "\xb7", "−": "-"}


class Page:
    def __init__(self, size: tuple[float, float] = A4):
        self.width, self.height = size
        self.ops: list[str] = []

    def text(self, x: float, y: float, text: str, size: float = 9.5, bold: bool = False,
             color: tuple[float, float, float] = (0.08, 0.08, 0.09)) -> None:
        font = "F2" if bold else "F1"
        self.ops.append(f"BT /{font} {size:g} Tf {_rgb(color)} rg {x:.2f} {self.height - y:.2f} Td "
                        f"({_escape(text)}) Tj ET")

    def line(self, x0: float, y0: float, x1: float, y1: float, width: float = 0.5,
             color: tuple[float, float, float] = (0.82, 0.84, 0.85)) -> None:
        self.ops.append(f"{width:g} w {_rgb(color)} RG {x0:.2f} {self.height - y0:.2f} m "
                        f"{x1:.2f} {self.height - y1:.2f} l S")

    def rect(self, x: float, y: float, w: float, h: float, color: tuple[float, float, float]) -> None:
        self.ops.append(f"{_rgb(color)} rg {x:.2f} {self.height - y - h:.2f} {w:.2f} {h:.2f} re f")


def text_width(text: str, size: float, bold: bool = False) -> float:
    """Approximate width (average Helvetica glyph width) for simple layout decisions."""
    return len(text) * size * (0.56 if bold else 0.52)


def render(page: Page, info: dict[str, str] | None = None) -> bytes:
    """The PDF file of one page; info: document information (Title, Author, Subject, CreationDate ...)."""
    content = "\n".join(page.ops).encode("cp1252", errors="replace")
    fonts = ("<< /Type /Font /Subtype /Type1 /BaseFont /{} /Encoding /WinAnsiEncoding >>")
    info_entries = " ".join(f"/{k} ({_escape(v)})" for k, v in (info or {}).items())
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page.width:.2f} {page.height:.2f}] "
         f"/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> /Contents 4 0 R >>").encode(),
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        fonts.format("Helvetica").encode(),
        fonts.format("Helvetica-Bold").encode(),
        f"<< {info_entries} /Producer (Virtual Factory MES) >>".encode("cp1252", errors="replace"),
    ]
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    trailer = b"trailer\n<< /Size %d /Root 1 0 R /Info 7 0 R >>\nstartxref\n%d\n%%%%EOF\n"
    out += trailer % (len(objects) + 1, xref)
    return bytes(out)


def _escape(text: str) -> str:
    for char, substitute in SUBSTITUTES.items():
        text = text.replace(char, substitute)
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _rgb(color: tuple[float, float, float]) -> str:
    return " ".join(f"{c:.3g}" for c in color)
