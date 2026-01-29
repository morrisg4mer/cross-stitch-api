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

def pixelate_to_grid(img: Image.Image, colors: int = 16, grid: int = 80):
    """
    Converte a imagem para um grid (grid x grid) com quantização de cores.
    Retorna uma imagem pequena (grid x grid).
    """
    img = img.convert("RGB")
    img_small = img.resize((grid, grid), Image.NEAREST)
    img_small = img_small.quantize(colors=colors).convert("RGB")
    return img_small

def upscale_to_target(img_small: Image.Image, grid: int, target_size: int = 2400):
    """
    Amplia a imagem para alta resolução, garantindo quadradinhos nítidos.
    target_size = tamanho final (largura/altura) em px
    """
    # garante que target_size seja múltiplo do grid
    cell_size = max(1, target_size // grid)
    final_size = grid * cell_size
    img_big = img_small.resize((final_size, final_size), Image.NEAREST)
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
    Desenha linhas de grade por cima da imagem.
    A cada `highlight_every` quadradinhos, desenha uma linha mais destacada.
    """
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    w, h = img.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    grid = w // cell_size

    # linhas verticais
    for i in range(grid + 1):
        x = i * cell_size
        if i % highlight_every == 0:
            draw.line([(x, 0), (x, h)], fill=highlight_line, width=highlight_width)
        else:
            draw.line([(x, 0), (x, h)], fill=normal_line, width=normal_width)

    # linhas horizontais
    for i in range(grid + 1):
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
    target_size: int = 2400,       # resolução final (quanto maior melhor)
    highlight_every: int = 10      # linha destacada a cada 10 quadradinhos
):
    contents = await file.read()
    img = Image.open(io.BytesIO(contents))
    img = ImageOps.exif_transpose(img)

    # 1) cria pixel art no grid
    img_small = pixelate_to_grid(img, colors=colors, grid=grid)

    # 2) amplia para alta resolução
    result, cell_size = upscale_to_target(img_small, grid=grid, target_size=target_size)

    # 3) desenha grade por cima
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
        "draw_grid": draw_grid,
        "target_size": target_size,
        "cell_size": cell_size,
        "highlight_every": highlight_every
    }
