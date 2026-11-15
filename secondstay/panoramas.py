"""Contact sheets of a scan's panoramas, and what was read from them.

Most commercial scans carry no wall geometry, so windows and exits cannot be read from data.
For those, ``build_sheet`` lays twelve panoramas spread across the scan onto one image, and a
vision model looks at the sheet and answers a few fixed questions. The answers are stored as a
"reading" next to the sheet and are always shown as read from images, never as measured.

Needs Pillow (``pip install pillow``). Sheets and readings live under data/raw/, which is
git-ignored: they are real interiors and must not be committed.
"""

import io
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from . import matterport

REPO_ROOT = Path(__file__).resolve().parent.parent
SHEET_DIR = REPO_ROOT / "data" / "raw" / "panoramas"
READING_DIR = REPO_ROOT / "data" / "raw" / "readings"
PANOS_PER_SHEET = 12
FACE_PX = 200
SIDE_FACES = (1, 2, 3, 4)  # the four horizontal faces of the skybox; 0 is up, 5 is down

PANO_QUERY = """
query($id: ID!) {
  model(id: $id) {
    panoLocations {
      id
      position { x y z }
      anchor { floor { label } }
      skybox(resolution: "low") { status children }
    }
  }
}
"""

# What the vision model is asked about each sheet. Kept here so the questions are on record.
QUESTIONS = """Each numbered strip is one 360-degree position inside a commercial space, shown as four
views side by side. For the whole sheet, answer in JSON:
  "panoramas": how many strips are on the sheet,
  "with_windows": in how many strips a window to the outside is visible,
  "stairs": how many separate staircases are visible across the sheet (0 if none),
  "exit_doors": how many separate doors marked with an EXIT sign are visible across the sheet,
  "indoor": true if most strips are inside a building, false if the scan is mostly outdoors,
  "space": one or two words for what the space is (open office, private offices, corridor, lobby, ...),
  "notes": one short sentence on anything that limits the reading.
Count only what is clearly visible. Do not guess."""


def spread(points: list, count: int) -> list:
    """Indexes of `count` points far apart from each other (farthest-point sampling)."""
    if len(points) <= count:
        return list(range(len(points)))
    chosen = [0]
    distance = [float("inf")] * len(points)
    while len(chosen) < count:
        last = points[chosen[-1]]
        for i, p in enumerate(points):
            d = sum((a - b) ** 2 for a, b in zip(p, last))
            distance[i] = min(distance[i], d)
        chosen.append(max(range(len(points)), key=lambda i: distance[i]))
    return sorted(chosen)


def _download(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def build_sheet(model_id: str) -> Optional[Path]:
    """Write the contact sheet for one scan and return its path, or None if it has no panoramas."""
    from PIL import Image, ImageDraw

    path = SHEET_DIR / f"{model_id}.jpg"
    if path.exists():
        return path
    places = [
        p for p in matterport._post(PANO_QUERY, {"id": model_id})["model"]["panoLocations"] or []
        if (p.get("skybox") or {}).get("status") == "available" and len(p["skybox"].get("children") or []) >= 5
    ]
    if not places:
        return None
    points = [(p["position"]["x"], p["position"]["y"], p["position"]["z"] * 3) for p in places]
    picked = [places[i] for i in spread(points, PANOS_PER_SHEET)]
    urls = [p["skybox"]["children"][face] for p in picked for face in SIDE_FACES]
    with ThreadPoolExecutor(max_workers=12) as pool:
        faces = list(pool.map(_download, urls))

    columns, rows = 2, (len(picked) + 1) // 2
    strip_w, strip_h = FACE_PX * len(SIDE_FACES), FACE_PX
    sheet = Image.new("RGB", (columns * strip_w + (columns - 1) * 8, rows * (strip_h + 8)), (10, 14, 22))
    draw = ImageDraw.Draw(sheet)
    for n, place in enumerate(picked):
        x0, y0 = (n % columns) * (strip_w + 8), (n // columns) * (strip_h + 8)
        for f in range(len(SIDE_FACES)):
            face = Image.open(io.BytesIO(faces[n * len(SIDE_FACES) + f])).convert("RGB").resize((FACE_PX, FACE_PX))
            sheet.paste(face, (x0 + f * FACE_PX, y0))
        draw.rectangle((x0, y0, x0 + 30, y0 + 18), fill=(0, 0, 0))
        draw.text((x0 + 5, y0 + 3), str(n + 1), fill=(255, 255, 255))
    SHEET_DIR.mkdir(parents=True, exist_ok=True)
    sheet.save(path, quality=82)
    return path


def reading(model_id: str) -> Optional[dict]:
    """What was read from this scan's sheet, or None if it has not been read."""
    path = READING_DIR / f"{model_id}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    if not isinstance(data.get("panoramas"), int) or data["panoramas"] <= 0:
        return None
    return data
