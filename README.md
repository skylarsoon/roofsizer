# JobNimbus Roof Sizer

A Python backend that accepts a roof image and uses AI to segment (outline) the roof automatically.

---

## What has been built so far

### 1. A web server with one endpoint: `POST /upload`

You send it an image file (JPG or PNG). It runs AI segmentation on the image and sends back a JSON response telling you:

- The filename you uploaded
- The image dimensions (`[height, width, channels]`)
- A `mask_b64` field — a base64-encoded black-and-white PNG where **white pixels = roof** and **black pixels = not roof**
- An `iou_score` — the AI's confidence in the mask (0 to 1, higher is better)

Example response:
```json
{
  "status": "ok",
  "filename": "roof.jpg",
  "image_shape": [1024, 768, 3],
  "mask_b64": "iVBORw0KGgo...",
  "iou_score": 0.91
}
```

### 2. SAM 2 integration (Meta's Segment Anything Model 2)

The AI doing the segmentation is [SAM 2](https://github.com/facebookresearch/sam2) by Meta. It's a state-of-the-art image segmentation model.

- The model is loaded **once at server startup** (not on every request — that would be very slow).
- We use **prompted mode**: instead of segmenting everything in the image, we give SAM 2 a single point prompt at the **center of the image** as a hint for where the roof is. SAM 2 then figures out which object at that point is the roof and draws a mask around it.
- SAM 2 returns 3 candidate masks. We automatically pick the one it's most confident about.

### 3. Project structure (router / controller / model pattern)

The code is split into three layers so it stays readable as it grows:

```
JobNimbusRoofSizer/
├── main.py                        # Starts the server; loads the AI model at boot
├── requirements.txt               # Python packages needed
│
├── routers/
│   └── upload_router.py           # Declares the /upload URL and HTTP method
│
├── controllers/
│   └── upload_controller.py       # All the logic: decode image, run AI, encode mask
│
├── models/
│   └── upload_models.py           # Defines the shape of the JSON response
│
└── core/
    └── sam_predictor.py           # Manages the AI model singleton and request locking
```

- **Router** — knows nothing about logic, just wires a URL to a function.
- **Controller** — does the actual work (decode image → run SAM 2 → encode result).
- **Model** — describes what the JSON response looks like (enforced by Pydantic).
- **Core** — infrastructure shared across the app (the AI model lives here).

---

## How to run

### First time setup

**1. Make sure you have Python 3.11**
```bash
python3.11 --version
```

**2. Create and activate a virtual environment**
```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

**3. Install dependencies**
```bash
pip install -r requirements.txt
```

> The first time you start the server, it will automatically download the SAM 2 model weights from HuggingFace (~180 MB). This only happens once — they get cached locally.

### Starting the server

```bash
.venv/bin/uvicorn main:app --reload
```

The `--reload` flag means the server restarts automatically when you edit a file. Remove it in production.

The server will be available at `http://127.0.0.1:8000`.

### Testing the endpoint

**With curl:**
```bash
curl -X POST http://127.0.0.1:8000/upload \
  -F "file=@/path/to/your/roof.jpg"
```

**With the built-in interactive docs** (no curl needed):

Open `http://127.0.0.1:8000/docs` in your browser. You'll see a visual interface where you can upload an image and see the response directly.

### Decoding the mask (optional)

The `mask_b64` in the response is a base64-encoded PNG. To convert it back to an image in Python:

```python
import base64, io
from PIL import Image

mask_b64 = "iVBORw0KGgo..."  # paste value from response
mask_bytes = base64.b64decode(mask_b64)
mask_img = Image.open(io.BytesIO(mask_bytes))
mask_img.save("mask.png")
```

---

## What's coming next

- GSD (Ground Sample Distance) logic to calculate real-world roof area from pixel counts
- Frontend UI for uploading images and viewing the mask overlay
