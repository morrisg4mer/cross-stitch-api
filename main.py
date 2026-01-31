from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageOps, ImageDraw, ImageEnhance, ImageFilter
import io
import base64

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def compute_grid_size(img: Image.Image, grid: int = 80):
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
    logo: melhora agressiva para bordas e definição
    """
    img = img.convert("RGB")

    if mode == "logo":
        # aumenta contraste e nitidez pra logo ficar limpa
        img = ImageEnhance.Contrast(img).enhance(1.6)
        img = ImageEnhance.Sharpness(img).enhance(2.2)
        img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=180, threshold=2))
    else:
        # foto: leve melhoria só pra ficar mais nítida
        img = ImageEnhance.Contrast(img).enhance(1.15)
        img = ImageEnhance.Sharpness(img).enhance(1.2)

    return img

def pixelate_to_grid(img: Image.Image, colors: int, grid_w: int, grid_h: int):
    img_small = img.resize((grid_w, grid_h), Image.Resampling.NEAREST)
    img_small = img_small.quantize(colors=colors, method=2).convert("RGB")
    return img_small

def upscale_to_target(img_small: Image.Image, grid_w: int, grid_h: int, target_size: int = 2400):
    bigger_side = max(grid_w, grid_h)
    cell_size = max(1, target_size // bigger_side)

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

@app.get("/")
def root():
    return {"status": "online"}

@app.post("/convert")
async def convert(
    file: UploadFile = File(...),
    colors: int = 24,
    grid: int = 80,
    mode: str = "photo",  # "photo" ou "logo"
    draw_grid: bool = True,
    target_size: int = 2400,
    highlight_every: int = 10
):
    contents = await file.read()
    img = Image.open(io.BytesIO(contents))
    img = ImageOps.exif_transpose(img)

    # 0) preprocess
    img = preprocess(img, mode=mode)

    # 1) grid proporcional
    grid_w, grid_h = compute_grid_size(img, grid=grid)

    # 2) pixeliza
    img_small = pixelate_to_grid(img, colors=colors, grid_w=grid_w, grid_h=grid_h)

    # 3) upscale HD
    result, cell_size = upscale_to_target(
        img_small,
        grid_w=grid_w,
        grid_h=grid_h,
        target_size=target_size
    )

    # 4) grade
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
        "mode": mode,
        "draw_grid": draw_grid,
        "target_size": target_size,
        "cell_size": cell_size,
        "highlight_every": highlight_every
    }
