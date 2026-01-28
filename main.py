from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageOps
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

@app.get("/")
def root():
    return {"status": "online"}

@app.post("/convert")
async def convert(
    file: UploadFile = File(...),
    colors: int = 16,
    grid: int = 80
):
    contents = await file.read()
    img = Image.open(io.BytesIO(contents))
    img = ImageOps.exif_transpose(img)

    result = pixelate(img, colors=colors, grid=grid)

    buf = io.BytesIO()
    result.save(buf, format="PNG")
    buf.seek(0)

    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    return {
        "ok": True,
        "image_base64": b64,
        "colors": colors,
        "grid": grid
    }
