"""Render the deterministic Autobolge README animation."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WIDTH, HEIGHT = 1200, 640
BG = (7, 10, 14)
PANEL = (11, 16, 22)
BAR = (22, 29, 38)
BORDER = (51, 65, 82)
TEXT = (215, 225, 238)
DIM = (105, 121, 140)
GREEN = (92, 224, 132)
CYAN = (88, 205, 232)
YELLOW = (239, 202, 93)
ORANGE = (255, 163, 82)
RED = (236, 91, 91)


def font(size: int, bold: bool = False):
    names = [
        "C:/Windows/Fonts/CascadiaMono.ttf" if not bold else "C:/Windows/Fonts/CascadiaMono-Bold.ttf",
        "C:/Windows/Fonts/consola.ttf",
    ]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


REGULAR = font(21)
SMALL = font(17)
BOLD = font(24, bold=True)
TITLE = font(26, bold=True)


def terminal(draw, box, title):
    x, y, w, h = box
    draw.rectangle((x, y, x + w, y + h), fill=PANEL, outline=BORDER, width=2)
    draw.rectangle((x + 1, y + 1, x + w - 1, y + 42), fill=BAR)
    for offset, color in ((18, RED), (42, YELLOW), (66, GREEN)):
        draw.ellipse((x + offset, y + 15, x + offset + 12, y + 27), fill=color)
    draw.text((x + 94, y + 9), title, font=SMALL, fill=TEXT)


def text_lines(draw, x, y, lines, spacing=31):
    for value, color in lines:
        draw.text((x, y), value, font=REGULAR, fill=color)
        y += spacing


def render(path: Path):
    frames = []
    program = "ubs`"
    phases = [
        ("boot", 0),
        ("catalog", 10),
        ("synthesize", 24),
        ("verify", 38),
        ("hold", 52),
    ]
    for phase, start in phases:
        for frame_no in range(start, start + (10 if phase != "hold" else 16)):
            image = Image.new("RGB", (WIDTH, HEIGHT), BG)
            draw = ImageDraw.Draw(image)
            draw.text((34, 22), "AUTOBOLGE", font=TITLE, fill=GREEN)
            draw.text((215, 27), "RELATIONAL MALBOLGE SYNTHESIS", font=SMALL, fill=DIM)

            terminal(draw, (28, 82, 560, 500), "synthesizer@autobolge:~")
            terminal(draw, (612, 82, 560, 500), "malbolge-runtime: verified")

            left = [
                ("$ autobolge synthesize --target AB", CYAN),
                ("", TEXT),
                ("relation", DIM),
                ('  input   = "AB"', TEXT),
                ('  output  = "AB"', TEXT),
                ("", TEXT),
                ("catalog", DIM),
                ("  299,593 programs indexed", YELLOW),
                ("  802 distinct outputs", YELLOW),
                ("", TEXT),
                ("beam", DIM),
                ("  guided state search active", ORANGE),
            ]
            text_lines(draw, 52, 145, left)

            if phase == "boot":
                typed = ""
                status = "initializing relational state..."
            elif phase == "catalog":
                typed = "ub"
                status = "catalog hit: partial echo"
            elif phase == "synthesize":
                count = min(len(program), max(0, frame_no - 24))
                typed = program[:count]
                status = "testing candidate transitions..."
            elif phase == "verify":
                typed = program
                status = "replaying candidate against I/O cases..."
            else:
                typed = program
                status = "verified relation: input prefix -> output prefix"

            draw.text((52, 505), f"candidate  {typed}", font=BOLD, fill=GREEN)
            draw.text((52, 548), status, font=SMALL, fill=DIM)

            right = [
                ("target relation", DIM),
                ('  "AB"  ->  "AB"', YELLOW),
                ("", TEXT),
                ("machine state", DIM),
                ("  A   65", TEXT),
                ("  C   04", TEXT),
                ("  D   40", TEXT),
                ("  steps 05", TEXT),
                ("", TEXT),
                ("canonical execution", DIM),
            ]
            text_lines(draw, 636, 145, right)

            output = "" if phase in ("boot", "catalog") else "AB"
            draw.text((636, 463), "OUTPUT", font=SMALL, fill=DIM)
            draw.text((636, 493), output, font=font(42, bold=True), fill=CYAN)
            if phase in ("verify", "hold"):
                draw.text((636, 552), "PASS  exact I/O match", font=BOLD, fill=GREEN)
            else:
                draw.text((636, 552), "running...", font=SMALL, fill=DIM)

            progress = min(1.0, max(0.0, (frame_no - start + 1) / (10 if phase != "hold" else 16)))
            draw.rectangle((28, 607, WIDTH - 28, 615), fill=BAR)
            draw.rectangle((28, 607, 28 + int((WIDTH - 56) * progress), 615), fill=GREEN)
            frames.append(image)

    path.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=110, loop=0, optimize=False)


if __name__ == "__main__":
    render(Path(__file__).resolve().parents[1] / "assets" / "autobolge.gif")
