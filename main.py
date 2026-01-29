from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageOps, ImageDraw
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

def compute_grid_size(img: Image.Image, grid: int = 80):
    """
    Mantém proporção:
    grid = tamanho do lado maior (ex: 80 quadradinhos no maior lado)
    retorna (grid_w, grid_h)
    """
    w, h = img.size

    if w >= h:
        # paisagem: fixa largura
        grid_w = grid
        grid_h = max(1, round(grid * (h / w)))
    else:
        # retrato: fixa altura
        grid_h = grid
        grid_w = max(1, round(grid * (w / h)))

    return grid_w, grid_h

def pixelate_to_grid(img: Image.Image, colors: int, grid_w: int, grid_h: int):
    img = img.convert("RGB")
    img_small = img.resize((grid_w, grid_h), Image.NEAREST)
    img_small = img_small.quantize(colors=colors).convert("RGB")
    return img_small

def upscale_to_target(img_small: Image.Image, grid_w: int, grid_h: int, target_size: int = 2400):
    """
    Amplia para alta resolução mantendo proporção.
    target_size = tamanho final do lado maior (px)
    """
    # calcula cell_size baseado no lado maior
    bigger_side = max(grid_w, grid_h)
    cell_size = max(1, target_size // bigger_side)

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
    Linha destacada a cada 10 quadradinhos (ou highlight_every).
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

    # novas opções
    draw_grid: bool = True,
    target_size: int = 2400,
    highlight_every: int = 10
):
    contents = await file.read()
    img = Image.open(io.BytesIO(contents))
    img = ImageOps.exif_transpose(img)

    # 1) calcula grid mantendo proporção
    grid_w, grid_h = compute_grid_size(img, grid=grid)

    # 2) pixeliza no grid proporcional
    img_small = pixelate_to_grid(img, colors=colors, grid_w=grid_w, grid_h=grid_h)

    # 3) amplia em alta resolução proporcional
    result, cell_size = upscale_to_target(
        img_small,
        grid_w=grid_w,
        grid_h=grid_h,
        target_size=target_size
    )

    # 4) desenha grade com destaque a cada 10
    if draw_grid:
        result = draw_grid_lines(
            result,
            cell_size=cell_size,
            highlight_every=highlight_every
        )

    buf = io.BytesIO()
    result.save(buf, format="PNG")
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
