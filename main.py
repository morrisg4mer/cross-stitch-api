from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageOps, ImageDraw, ImageEnhance, ImageFilter, ImageFont
import io
import base64

app = FastAPI()

# Permite Lovable chamar sua API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Símbolos (para o gráfico)
# -----------------------------
SYMBOLS = list("●■▲◆✖✚✦✧★☆☘☀☁☂☯☮♠♣♥♦☾☽") + list("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")

# -----------------------------
# Utilitários
# -----------------------------

def compute_grid_size(img: Image.Image, grid: int = 80):
    """
    Mantém proporção.
    grid = tamanho do lado maior em pontos.
    """
    w, h = img.size
    if w >= h:
        grid_w = grid
        grid_h = max(1, round(grid * (h / w)))
    else:
        grid_h = grid
        grid_w = max(1, round(grid * (w / h)))
    return grid_w, grid_h

def preprocess(img: Image.Image, mode: str):
    """
    photo: leve melhoria
    logo: melhora agressiva para bordas
    """
    img = img.convert("RGB")

    if mode == "logo":
        img = ImageEnhance.Contrast(img).enhance(1.8)
        img = ImageEnhance.Sharpness(img).enhance(2.6)
        img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=200, threshold=2))
    else:
        img = ImageEnhance.Contrast(img).enhance(1.15)
        img = ImageEnhance.Sharpness(img).enhance(1.2)

    return img

def pixelate_to_grid(img: Image.Image, colors: int, grid_w: int, grid_h: int):
    img_small = img.resize((grid_w, grid_h), Image.Resampling.NEAREST)
    img_small = img_small.quantize(colors=colors, method=2).convert("RGB")
    return img_small

def upscale_to_target(img_small: Image.Image, grid_w: int, grid_h: int, target_size: int = 2400):
    bigger_side = max(grid_w, grid_h)
    cell_size = max(10, target_size // bigger_side)  # mínimo pra caber símbolo

    final_w = grid_w * cell_size
    final_h = grid_h * cell_size

    img_big = img_small.resize((final_w, final_h), Image.Resampling.NEAREST)
    return img_big, cell_size

def draw_grid_lines(
    img: Image.Image,
    cell_size: int,
    highlight_every: int = 10,
    normal_line=(0, 0, 0, 35),
    highlight_line=(0, 0, 0, 120),
    normal_width: int = 1,
    highlight_width: int = 2
):
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    w, h = img.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    grid_w = w // cell_size
    grid_h = h // cell_size

    for i in range(grid_w + 1):
        x = i * cell_size
        if i % highlight_every == 0:
            draw.line([(x, 0), (x, h)], fill=highlight_line, width=highlight_width)
        else:
            draw.line([(x, 0), (x, h)], fill=normal_line, width=normal_width)

    for i in range(grid_h + 1):
        y = i * cell_size
        if i % highlight_every == 0:
            draw.line([(0, y), (w, y)], fill=highlight_line, width=highlight_width)
        else:
            draw.line([(0, y), (w, y)], fill=normal_line, width=normal_width)

    return Image.alpha_composite(img, overlay)

def build_palette_and_symbol_map(img_small: Image.Image):
    colors = img_small.getcolors(maxcolors=999999) or []
    colors_sorted = sorted(colors, key=lambda x: x[0], reverse=True)
    palette = [rgb for _, rgb in colors_sorted]

    symbol_map = {}
    for idx, rgb in enumerate(palette):
        symbol_map[rgb] = SYMBOLS[idx % len(SYMBOLS)]
    return palette, symbol_map

def get_font(cell_size: int):
    size = max(10, int(cell_size * 0.55))
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size=size)
    except:
        return ImageFont.load_default()

def draw_symbols(img: Image.Image, img_small: Image.Image, cell_size: int, symbol_map: dict):
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    w, h = img.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    grid_w, grid_h = img_small.size
    font = get_font(cell_size)

    for y in range(grid_h):
        for x in range(grid_w):
            rgb = img_small.getpixel((x, y))
            sym = symbol_map.get(rgb, "?")

            cx = x * cell_size + cell_size // 2
            cy = y * cell_size + cell_size // 2

            bbox = draw.textbbox((0, 0), sym, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]

            draw.text((cx - tw / 2, cy - th / 2), sym, fill=(0, 0, 0, 220), font=font)

    return Image.alpha_composite(img, overlay)

def draw_legend(img: Image.Image, palette: list, symbol_map: dict, cell_size: int):
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    w, h = img.size
    legend_h = max(140, int(cell_size * 6))
    new_img = Image.new("RGBA", (w, h + legend_h), (255, 255, 255, 255))
    new_img.paste(img, (0, 0))

    draw = ImageDraw.Draw(new_img)
    font = get_font(max(18, int(cell_size * 0.6)))

    padding = 20
    x0 = padding
    y0 = h + 25
    box = max(22, int(cell_size * 0.8))
    gap = 14

    max_per_row = max(1, (w - padding * 2) // (box * 3))

    draw.text((padding, h + 5), "Legenda (cor → símbolo)", fill=(0, 0, 0, 255), font=font)

    for i, rgb in enumerate(palette):
        sym = symbol_map.get(rgb, "?")
        row = i // max_per_row
        col = i % max_per_row

        xx = x0 + col * (box * 3)
        yy = y0 + row * (box + gap)

        draw.rectangle([xx, yy, xx + box, yy + box], fill=rgb + (255,), outline=(0, 0, 0, 120))
        draw.text((xx + box + 10, yy + 2), sym, fill=(0, 0, 0, 255), font=font)

    return new_img

# -----------------------------
# TEXTO -> IMAGEM BASE
# -----------------------------

FONTS = {
    "default": None,  # Pillow default
    "dejavu": "DejaVuSans.ttf",
}

def make_text_image(text: str, font_name: str = "dejavu", padding: int = 60):
    """
    Gera uma imagem branca com texto centralizado.
    Depois ela vai ser convertida em ponto cruz.
    """
    text = (text or "").strip()
    if not text:
        text = " "

    # canvas grande para depois reduzir com qualidade
    W, H = 1800, 900
    img = Image.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # fonte grande
    font_size = 220
    try:
        if FONTS.get(font_name):
            font = ImageFont.truetype(FONTS[font_name], font_size)
        else:
            font = ImageFont.load_default()
    except:
        font = ImageFont.load_default()

    # quebra linha simples
    lines = text.split("\n")

    # calcula altura total
    line_heights = []
    line_widths = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_widths.append(bbox[2] - bbox[0])
        line_heights.append(bbox[3] - bbox[1])

    total_h = sum(line_heights) + (len(lines) - 1) * 20
    y = (H - total_h) // 2

    for i, line in enumerate(lines):
        lw = line_widths[i]
        lh = line_heights[i]
        x = (W - lw) // 2
        draw.text((x, y), line, font=font, fill=(0, 0, 0))
        y += lh + 20

    # recorta bordas vazias (mantendo margem)
    bbox = ImageOps.invert(img.convert("L")).getbbox()
    if bbox:
        x1, y1, x2, y2 = bbox
        x1 = max(0, x1 - padding)
        y1 = max(0, y1 - padding)
        x2 = min(W, x2 + padding)
        y2 = min(H, y2 + padding)
        img = img.crop((x1, y1, x2, y2))

    return img

# -----------------------------
# Pipeline comum
# -----------------------------

def generate_pattern(
    img: Image.Image,
    colors: int,
    grid: int,
    mode: str,
    target_size: int,
    draw_grid: bool,
    highlight_every: int,
    draw_symbols_flag: bool,
    draw_legend_flag: bool
):
    img = preprocess(img, mode=mode)

    grid_w, grid_h = compute_grid_size(img, grid=grid)
    img_small = pixelate_to_grid(img, colors=colors, grid_w=grid_w, grid_h=grid_h)

    result, cell_size = upscale_to_target(
        img_small,
        grid_w=grid_w,
        grid_h=grid_h,
        target_size=target_size
    )

    palette, symbol_map = build_palette_and_symbol_map(img_small)

    if draw_symbols_flag:
        result = draw_symbols(result, img_small, cell_size, symbol_map)

    if draw_grid:
        result = draw_grid_lines(result, cell_size=cell_size, highlight_every=highlight_every)

    if draw_legend_flag:
        result = draw_legend(result, palette, symbol_map, cell_size)

    return result, {
        "grid_w": grid_w,
        "grid_h": grid_h,
        "cell_size": cell_size,
        "palette_size": len(palette)
    }

# -----------------------------
# Rotas
# -----------------------------

@app.get("/")
def root():
    return {"status": "online"}

@app.post("/convert")
async def convert(
    file: UploadFile = File(...),
    colors: int = 24,
    grid: int = 80,
    mode: str = "photo",  # photo/logo
    target_size: int = 2400,
    draw_grid: bool = True,
    highlight_every: int = 10,
    draw_symbols_flag: bool = True,
    draw_legend_flag: bool = True
):
    contents = await file.read()
    img = Image.open(io.BytesIO(contents))
    img = ImageOps.exif_transpose(img)

    result, meta = generate_pattern(
        img=img,
        colors=colors,
        grid=grid,
        mode=mode,
        target_size=target_size,
        draw_grid=draw_grid,
        highlight_every=highlight_every,
        draw_symbols_flag=draw_symbols_flag,
        draw_legend_flag=draw_legend_flag
    )

    buf = io.BytesIO()
    result.convert("RGBA").save(buf, format="PNG")
    buf.seek(0)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    return {
        "ok": True,
        "image_base64": b64,
        "colors": colors,
        "grid": grid,
        "mode": mode,
        "target_size": target_size,
        "draw_grid": draw_grid,
        "highlight_every": highlight_every,
        "draw_symbols": draw_symbols_flag,
        "draw_legend": draw_legend_flag,
        **meta
    }

@app.post("/text")
async def text_to_pattern(
    text: str,
    font: str = "dejavu",
    colors: int = 2,
    grid: int = 70,
    mode: str = "logo",
    target_size: int = 2400,
    draw_grid: bool = True,
    highlight_every: int = 10,
    draw_symbols_flag: bool = True,
    draw_legend_flag: bool = False
):
    """
    Converte TEXTO para gráfico de ponto cruz.
    """
    img = make_text_image(text=text, font_name=font)

    result, meta = generate_pattern(
        img=img,
        colors=colors,
        grid=grid,
        mode=mode,
        target_size=target_size,
        draw_grid=draw_grid,
        highlight_every=highlight_every,
        draw_symbols_flag=draw_symbols_flag,
        draw_legend_flag=draw_legend_flag
    )

    buf = io.BytesIO()
    result.convert("RGBA").save(buf, format="PNG")
    buf.seek(0)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    return {
        "ok": True,
        "image_base64": b64,
        "text": text,
        "font": font,
        "colors": colors,
        "grid": grid,
        "mode": mode,
        "target_size": target_size,
        "draw_grid": draw_grid,
        "highlight_every": highlight_every,
        "draw_symbols": draw_symbols_flag,
        "draw_legend": draw_legend_flag,
        **meta
    }
