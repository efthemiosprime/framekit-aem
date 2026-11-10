"""Figma REST API access (read-only): nodes, rendered images.

Docs: https://www.figma.com/developers/api  — needs a personal access token
in FIGMA_TOKEN. Node IDs may be given as "1:2" or "1-2".
"""
import urllib.parse

from . import net

API = "https://api.figma.com/v1"


def normalise_id(node_id):
    return node_id.replace("-", ":") if ";" not in node_id else node_id


class FigmaClient:
    def __init__(self, token, file_key, fetch_json=net.get_json, fetch_bytes=net.request):
        self.file_key = file_key
        self._headers = {"X-Figma-Token": token}
        self._fetch_json = fetch_json
        self._fetch_bytes = fetch_bytes

    def nodes(self, node_ids, depth=None):
        """Return {node_id: {"document": ..., "components": ..., "componentSets": ...}}."""
        ids = ",".join(normalise_id(i) for i in node_ids)
        query = {"ids": ids}
        if depth is not None:
            query["depth"] = str(depth)
        url = f"{API}/files/{self.file_key}/nodes?{urllib.parse.urlencode(query)}"
        data = self._fetch_json(url, headers=self._headers)
        missing = [i for i, v in data.get("nodes", {}).items() if v is None]
        if missing:
            raise net.HttpError(f"Figma did not return nodes: {', '.join(missing)}")
        return data["nodes"]

    def image_urls(self, node_ids, fmt="png", scale=2):
        ids = ",".join(normalise_id(i) for i in node_ids)
        query = urllib.parse.urlencode({"ids": ids, "format": fmt, "scale": str(scale)})
        data = self._fetch_json(f"{API}/images/{self.file_key}?{query}", headers=self._headers)
        if data.get("err"):
            raise net.HttpError(f"Figma image export failed: {data['err']}")
        urls = data.get("images", {})
        empty = [i for i, u in urls.items() if not u]
        if empty:
            raise net.HttpError(f"Figma rendered no image for: {', '.join(empty)}")
        return urls

    def image_fill_urls(self):
        """{imageRef: url} for every raster fill in the file (original resolution)."""
        data = self._fetch_json(f"{API}/files/{self.file_key}/images", headers=self._headers)
        return data.get("meta", {}).get("images", {})

    def fill_image_ref(self, node_id):
        """imageRef of the first visible IMAGE fill on a node (e.g. a hero background)."""
        doc = next(iter(self.nodes([node_id], depth=0).values()))["document"]
        for fill in doc.get("fills", []):
            if fill.get("type") == "IMAGE" and fill.get("visible", True) and fill.get("imageRef"):
                return fill["imageRef"]
        raise net.HttpError(f"Node {node_id} has no visible image fill")

    def download(self, url):
        return self._fetch_bytes(url)


# -- tree helpers ---------------------------------------------------------------
def walk(node, parent_is_instance=False):
    """Yield (node, inside_instance) depth-first."""
    yield node, parent_is_instance
    inside = parent_is_instance or node.get("type") == "INSTANCE"
    for child in node.get("children", []):
        yield from walk(child, inside)


def relative_box(node, frame):
    box, origin = node.get("absoluteBoundingBox"), frame.get("absoluteBoundingBox")
    if not box or not origin:
        return None
    return [round(box["x"] - origin["x"]), round(box["y"] - origin["y"]),
            round(box["width"]), round(box["height"])]


# -- cropped image fills ---------------------------------------------------------------
def fill_image(node_doc):
    """(imageRef, imageTransform or None) of a node's first visible IMAGE fill."""
    for fill in node_doc.get("fills", []):
        if fill.get("type") == "IMAGE" and fill.get("visible", True) and fill.get("imageRef"):
            return fill["imageRef"], fill.get("imageTransform")
    raise net.HttpError(f"Node {node_doc.get('id')} has no visible image fill")


def crop_rect(transform, width, height):
    """Pixel crop (x, y, w, h) of the original image that a Figma crop transform shows.

    transform = [[sx, 0, tx], [0, sy, ty]]: the visible part starts at (tx, ty) and
    spans (sx, sy), all as fractions of the original image (verified on a production
    mobile hero: [[0.128, 0, 0.569], [0, 0.308, 0.444]] of a 4096×3237 original).
    """
    (sx, kx, tx), (ky, sy, ty) = transform
    if abs(kx) > 1e-6 or abs(ky) > 1e-6:
        raise ValueError("rotated/skewed image fills are not supported; export the layer instead (figmaNode)")
    x, y = round(tx * width), round(ty * height)
    w, h = round(sx * width), round(sy * height)
    return max(0, x), max(0, y), min(w, width - max(0, x)), min(h, height - max(0, y))
