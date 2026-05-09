import base64, io, json
import numpy as np
from PIL import Image
data = json.load(open("response.json"))
original = Image.open("test_roof1.png").convert("RGBA")
mask_bytes = base64.b64decode(data["mask_b64"])
mask = Image.open(io.BytesIO(mask_bytes)).convert("L")  # grayscale
# Make a semi-transparent green overlay where the mask is white
overlay = Image.new("RGBA", original.size, (0, 0, 0, 0))
green = Image.new("RGBA", original.size, (0, 255, 0, 120))  # green, 47% opacity
overlay.paste(green, mask=mask)
result = Image.alpha_composite(original, overlay)
result.save("overlay.png")
print("Saved overlay.png")