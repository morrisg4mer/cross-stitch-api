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

def pixelate(img: Image.Image, colors: int = 16, grid: int = 80, scale: int = 12):
    img = img.convert("RGB")
    img_small = img.resize((grid, grid), Image.NEAREST)
    img_small = img_small.quantize(colors=colors).convert("RGB")
    img_big = img_small.resize((grid * scale, grid * scale), Image.NEAREST)
    return img_big

def draw_grid_lines(img: Image.Image, cell_size: int = 12, line_color=(0, 0, 0, 70)):
    """
    Desenha linhas de grade (papel quadriculado) por cima da imagem.
    cell_size = tamanho do quadradinho em pixels
    line_color = RGBA com transparência
    """
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    w, h = img.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # linhas verticais
    for x in range(0, w + 1, cell_size):
        draw.line([(x, 0), (x, h)], fill=line_color, width=1)

    # linhas horizontais
    for y in range(0, h + 1, cell_size):
        draw.line([(0, y), (w, y)], fill=line_color, width=1)

    return Image.alpha_composite(img, overlay)

@app.get("/")
def root():
    return {"status": "online"}

@app.post("/convert")
async def convert(
    file: UploadFile = File(...),
    colors: int = 16,
    grid: int = 80,
    draw_grid: bool = False,
    cell_size: int = 12
):
    contents = await file.read()
    img = Image.open(io.BytesIO(contents))
    img = ImageOps.exif_transpose(img)

    # 1) gera pixel art
    result = pixelate(img, colors=colors, grid=grid)

    # 2) desenha o papel grafo (quadradinhos) se pedir
    if draw_grid:
        result = draw_grid_lines(result, cell_size=cell_size)

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
        "cell_size": cell_size
    }
