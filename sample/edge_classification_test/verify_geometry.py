import base64, io, json, math
import cv2
import numpy as np
from PIL import Image

data = json.load(open("response.json"))

# Decode the mask
mask_bytes = base64.b64decode(data["mask_b64"])
mask = np.array(Image.open(io.BytesIO(mask_bytes)).convert("L"))
h, w = mask.shape

# Rebuild the contour as an OpenCV-compatible array
contour_pts = np.array(data["geometry"]["contour"], dtype=np.int32)
contour = contour_pts.reshape((-1, 1, 2))

# Draw on a copy of the original image
img = cv2.imread("test_roof1.png")
n = len(contour_pts)

COLORS = {
    "eave":  (0, 255, 0),    # green
    "ridge": (0, 0, 255),    # red
    "rake":  (255, 165, 0),  # orange
    "other": (128, 128, 128) # gray
}

for i in range(n):
    x1, y1 = contour_pts[i]
    x2, y2 = contour_pts[(i + 1) % n]

    edge_len = math.hypot(x2 - x1, y2 - y1)
    if edge_len == 0:
        continue

    angle = math.degrees(math.atan2(abs(y2 - y1), abs(x2 - x1)))
    mid_y = (y1 + y2) / 2.0

    if angle <= 20:
        color = COLORS["eave"] if mid_y > h / 2 else COLORS["ridge"]
    elif angle <= 70:
        color = COLORS["rake"]
    else:
        color = COLORS["other"]

    cv2.line(img, (x1, y1), (x2, y2), color, thickness=3)

# Legend
for i, (label, color) in enumerate(COLORS.items()):
    cv2.putText(img, label, (10, 30 + i * 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

cv2.imwrite("verify_geometry.png", img)
print("Saved verify_geometry.png")
print("Pixel area :", data["geometry"]["pixel_area"])
print("Perimeter  :", data["geometry"]["perimeter_px"])
print("Edges      :", data["geometry"]["edge_classifications"])