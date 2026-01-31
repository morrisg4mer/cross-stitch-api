from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageOps, ImageDraw
import io
import base64
import math

app = FastAPI()

# Permite Lovable chamar sua API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def compute_grid_size(img: Image.Image, grid: int = 80):
    """
    Mantém proporção.
    grid = quantidade de quadradinhos no maior lado.
    Retorna (grid_w, grid_h).
    """
    w, h = img.size
    if w >= h:
        grid_w = grid
        grid_h = max(1, round(grid * (h / w)))
    else:
        grid_h = grid
        grid_w = max(1, round(grid * (w / h)))
    return grid_w, grid_h


def dominant_color_block(block: Image.Image):
    """
    Cor dominante de um bloco (método estilo Excel).
    Rápido e com bom resultado.
    """
    # reduz o bloco para acelerar
    block = block.convert("RGB")
    small = block.resize((16, 16), Image.BILINEAR)

    # pega cor mais frequente
    colors = small.getcolors(16 * 16)
    if not colors:
        return (255, 255, 255)
    # ordena por frequência
    colors.sort(key=lambda x: x[0], reverse=True)
    return colors[0][1]


def mosaic_from_original(img: Image.Image, grid_w: int, grid_h: int):
    """
    Cria mosaico SEM distorcer:
    cada quadradinho representa um bloco da imagem original.
    Resultado: imagem pequena (grid_w x grid_h) com cor por célula.
    """
    img = img.convert("RGB")
    w, h = img.size

    cell_w = w / grid_w
    cell_h = h / grid_h

    out = Image.new("RGB", (grid_w, grid_h), (255, 255, 255))
    px = out.load()

    for gy in range(grid_h):
        for gx in range(grid_w):
            left = int(gx * cell_w)
            right = int((gx + 1) * cell_w)
            top = int(gy * cell_h)
            bottom = int((gy + 1) * cell_h)

            # garante pelo menos 1px
            right = max(right, left + 1)
            bottom = max(bottom, top + 1)

            block = img.crop((left, top, right, bottom))
            px[gx, gy] = dominant_color_block(block)

    return out


def quantize_colors(img_small: Image.Image, colors: int):
    """
    Reduz para N cores.
    """
    return img_small.quantize(colors=colors, method=Image.MEDIANCUT).convert("RGB")


def upscale_to_target(img_small: Image.Image, grid_w: int, grid_h: int, target_size: int = 2400):
    """
    Amplia para alta resolução mantendo proporção.
    target_size = tamanho final do lado maior (px)
    """
    bigger_side = max(grid_w, grid_h)
    cell_size = max(8, target_size // bigger_side)  # mínimo 8px por célula

    final_w = grid_w * cell_size
    final_h = grid_h * cell_size

    img_big = img_small.resize((final_w, final_h), Image.NEAREST)
    return img_big, cell_size


def draw_grid_lines(
    img: Image.Image,
    cell_size: int,
    highlight_every: int = 10,
    normal_line=(0, 0, 0, 40),
    highlight_line=(0, 0, 0, 120),
    normal_width: int = 1,
    highlight_width: int = 2
):
    """
    Desenha grade por cima.
    Linha destacada a cada 10 quadradinhos.
    """
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    w, h = img.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    grid_w = w // cell_size
    grid_h = h // cell_size

    # verticais
    for i in range(grid_w + 1):
        x = i * cell_size
        if i % highlight_every == 0:
            draw.line([(x, 0), (x, h)], fill=highlight_line, width=highlight_width)
        else:
            draw.line([(x, 0), (x, h)], fill=normal_line, width=normal_width)

    # horizontais
    for i in range(grid_h + 1):
        y = i * cell_size
        if i % highlight_every == 0:
            draw.line([(0, y), (w, y)], fill=highlight_line, width=highlight_width)
        else:
            draw.line([(0, y), (w, y)], fill=normal_line, width=normal_width)

    return Image.alpha_composite(img, overlay)


@app.get("/")
def root():
    return {"status": "online"}


@app.post("/convert")
async def convert(
    file: UploadFile = File(...),
    colors: int = 16,
    grid: int = 80,

    draw_grid: bool = True,
    target_size: int = 2400,
    highlight_every: int = 10
):
    contents = await file.read()
    img = Image.open(io.BytesIO(contents))
    img = ImageOps.exif_transpose(img)

    # limita tamanho máximo pra não pesar no Render
    MAX_SIDE = 2200
    w, h = img.size
    bigger = max(w, h)
    if bigger > MAX_SIDE:
        scale = MAX_SIDE / bigger
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    # 1) calcula grid proporcional
    grid_w, grid_h = compute_grid_size(img, grid=grid)

    # 2) cria mosaico pelo ORIGINAL (excel style)
    img_small = mosaic_from_original(img, grid_w=grid_w, grid_h=grid_h)

    # 3) reduz para N cores
    img_small = quantize_colors(img_small, colors=colors)

    # 4) amplia em alta resolução
    result, cell_size = upscale_to_target(
        img_small,
        grid_w=grid_w,
        grid_h=grid_h,
        target_size=target_size
    )

    # 5) desenha grade
    if draw_grid:
        result = draw_grid_lines(
            result,
            cell_size=cell_size,
            highlight_every=highlight_every
        )

    buf = io.BytesIO()
    result.save(buf, format="PNG", optimize=True)
    buf.seek(0)

    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    return {
        "ok": True,
        "image_base64": b64,
        "colors": colors,
        "grid": grid,
        "grid_w": grid_w,
        "grid_h": grid_h,
        "draw_grid": draw_grid,
        "target_size": target_size,
        "cell_size": cell_size,
        "highlight_every": highlight_every
    }
