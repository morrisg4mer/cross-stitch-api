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

# ----------------------------
# Helpers de ajuste de imagem
# ----------------------------

def preprocess(img: Image.Image, mode: str):
    """
    mode:
      - photo: leve melhoria e mais natural
      - logo: deixa bordas mais definidas
    """
    img = img.convert("RGB")

    if mode == "logo":
        img = ImageEnhance.Contrast(img).enhance(1.8)
        img = ImageEnhance.Sharpness(img).enhance(2.4)
        img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=220, threshold=2))
    else:
        img = ImageEnhance.Contrast(img).enhance(1.20)
        img = ImageEnhance.Sharpness(img).enhance(1.25)

    return img


def fit_to_square(img: Image.Image, size: int, fit: str = "pad", bg=(255, 255, 255)):
    """
    Transforma a imagem em quadrada sem distorcer:
    fit="pad"  -> adiciona bordas (melhor pra foto)
    fit="crop" -> corta no centro (melhor pra logo)
    """
    img = img.convert("RGB")

    if fit == "crop":
        # crop central
        w, h = img.size
        side = min(w, h)
        left = (w - side) // 2
        top = (h - side) // 2
        img = img.crop((left, top, left + side, top + side))
        return img.resize((size, size), Image.Resampling.LANCZOS)

    # pad (letterbox)
    w, h = img.size
    scale = min(size / w, size / h)
    nw, nh = int(w * scale), int(h * scale)
    img_resized = img.resize((nw, nh), Image.Resampling.LANCZOS)

    canvas = Image.new("RGB", (size, size), bg)
    x = (size - nw) // 2
    y = (size - nh) // 2
    canvas.paste(img_resized, (x, y))
    return canvas


def pixelate_points(img: Image.Image, points: int, colors: int, mode: str):
    """
    Converte para um grid de "points x points" (pano real).
    IMPORTANTE:
      - Redução: LANCZOS (fica MUITO melhor)
      - Quantização:
          photo -> dithering ON
          logo  -> dithering OFF
    """
    # 1) reduz com qualidade (mantém detalhes)
    img_small = img.resize((points, points), Image.Resampling.LANCZOS)

    # 2) quantiza com ou sem dithering
    if mode == "photo":
        # dithering ligado (bom pra foto em poucos pontos)
        img_small = img_small.quantize(colors=colors, method=2, dither=Image.Dither.FLOYDSTEINBERG).convert("RGB")
    else:
        # logo: sem dithering pra manter blocos chapados
        img_small = img_small.quantize(colors=colors, method=2, dither=Image.Dither.NONE).convert("RGB")

    return img_small


def upscale_to_target(img_small: Image.Image, points: int, target_size: int = 2400):
    """
    Amplia mantendo pixels perfeitos (NEAREST).
    """
    cell_size = max(1, target_size // points)
    final_size = points * cell_size
    img_big = img_small.resize((final_size, final_size), Image.Resampling.NEAREST)
    return img_big, cell_size


def draw_grid_lines(
    img: Image.Image,
    cell_size: int,
    highlight_every: int = 10,
    normal_line=(0, 0, 0, 35),
    highlight_line=(0, 0, 0, 130),
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

    # verticais
    for i in range(grid_w + 1):
        x = i * cell_size
        if highlight_every > 0 and i % highlight_every == 0:
            draw.line([(x, 0), (x, h)], fill=highlight_line, width=highlight_width)
        else:
            draw.line([(x, 0), (x, h)], fill=normal_line, width=normal_width)

    # horizontais
    for i in range(grid_h + 1):
        y = i * cell_size
        if highlight_every > 0 and i % highlight_every == 0:
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

    # pano: quantidade de quadradinhos (lado)
    points: int = 70,  # 20,30,50,60,70,100

    # cores
    colors: int = 24,

    # modo: foto ou logo
    mode: str = "photo",  # "photo" ou "logo"

    # encaixe sem distorcer
    fit: str = "pad",  # "pad" ou "crop"

    # grade
    draw_grid: bool = True,
    highlight_every: int = 10,

    # resolução final
    target_size: int = 2400,
):
    contents = await file.read()
    img = Image.open(io.BytesIO(contents))
    img = ImageOps.exif_transpose(img)

    # 0) preprocess
    img = preprocess(img, mode=mode)

    # 1) encaixa sem distorcer (vira quadrado)
    img_sq = fit_to_square(img, size=1200, fit=fit)

    # 2) transforma em pontos reais do pano
    img_small = pixelate_points(img_sq, points=points, colors=colors, mode=mode)

    # 3) upscale HD
    result, cell_size = upscale_to_target(img_small, points=points, target_size=target_size)

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
        "points": points,
        "colors": colors,
        "mode": mode,
        "fit": fit,
        "draw_grid": draw_grid,
        "highlight_every": highlight_every,
        "target_size": target_size,
        "cell_size": cell_size
    }
