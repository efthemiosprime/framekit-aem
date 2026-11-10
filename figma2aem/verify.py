"""Figma ↔ browser parity spec.

page.json "verify":
{
  "url": "http://localhost:4502/content/site/us/en.html?wcmmode=disabled",
  "tolerance": 2,
  "viewports": [ {"width": 1440, "figmaFrame": "1:2"}, {"width": 360, "figmaFrame": "1:4"} ]
}
Each component node with "verify": {"figma": "<layer name>", "selector": "<css>"}
becomes one check per viewport. Layers are matched by name inside the frame
(instance children get new IDs per frame, names stay stable). A check whose
layer is absent or hidden in a frame is skipped for that viewport.

Geometry is relative to the frame's top-left; the probe measures relative to
the document, so frames must start at the page top (header included).
"""
from .config import require
from .figma_client import relative_box, walk
from .page import walk_spec


def checks_from_page(page_spec):
    """"figma" may be one layer name or a list (first one present in the frame wins,
    e.g. ["Hero_Desktop", "Hero_Mobile"])."""
    checks = []
    for node in walk_spec(page_spec["body"]):
        spec = node.get("verify")
        if spec:
            names = require(spec, "figma", node["name"])
            checks.append({"label": node["name"], "figma": [names] if isinstance(names, str) else list(names),
                           "selector": require(spec, "selector", node["name"]),
                           "index": spec.get("index", 0),            # nth DOM match of selector
                           "figmaIndex": spec.get("figmaIndex", 0)})  # nth layer with that name
    return checks


def frame_boxes(frame_doc, names):
    """{layer name: [boxes in document order]} for visible layers."""
    found = {}
    for node, _ in walk(frame_doc):
        if node.get("name") in names and node.get("visible", True):
            box = relative_box(node, frame_doc)
            if box:
                found.setdefault(node["name"], []).append(box)
    return found


def build_spec(page_spec, frames_by_id):
    verify = require(page_spec, "verify", "page.json")
    checks = checks_from_page(page_spec)
    names = {n for c in checks for n in c["figma"]}
    viewports = []
    for vp in require(verify, "viewports", "page.json verify"):
        frame = frames_by_id[vp["figmaFrame"].replace("-", ":")]["document"]
        boxes = frame_boxes(frame, names)
        vp_checks = []
        for check in checks:
            nth = check["figmaIndex"]
            layer = next((n for n in check["figma"] if len(boxes.get(n, [])) > nth), None)
            if layer:
                vp_checks.append({**check, "figma": layer, "expected": boxes[layer][nth]})
        viewports.append({"width": vp["width"], "figmaFrame": vp["figmaFrame"],
                          # live header height minus the Figma frame's nav height (e.g. 70 - 72 = -2)
                          "headerOffset": vp.get("headerOffset", 0), "checks": vp_checks})
    return {"url": require(verify, "url", "page.json verify"),
            "tolerance": verify.get("tolerance", 2), "viewports": viewports}
