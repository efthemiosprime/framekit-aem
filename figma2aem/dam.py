"""Local image files → dam:Asset docview entries.

page.json "assets":
[
  {"file": "hero.png", "title": "Alt / DAM title", "figmaNode": "10:20", "scale": 2}
]
"file" lives in project assetsDir; "figmaNode" is only used by export-assets.
"""
import hashlib
import struct
from datetime import datetime, timezone

from . import jcr
from .config import ConfigError, require

MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".svg": "image/svg+xml", ".webp": "image/webp", ".gif": "image/gif"}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def image_size(data, suffix):
    if suffix == ".png":
        if data[:8] != PNG_SIGNATURE:
            raise ConfigError("File has a .png name but is not a PNG")
        return struct.unpack(">II", data[16:24])
    return None


def asset_entries(asset, project):
    file_name = require(asset, "file", "assets")
    src = project.assets_dir / file_name
    if not src.is_file():
        raise ConfigError(f"Asset missing: {src} (run export-assets or add the file)")
    data = src.read_bytes()
    if not data:
        raise ConfigError(f"Asset is empty: {src}")
    suffix = src.suffix.lower()
    mime = MIME.get(suffix)
    if not mime:
        raise ConfigError(f"Unsupported asset type: {src.name}")

    now = jcr.Date(datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"))
    meta = {"jcr:primaryType": "nt:unstructured", "dam:MIMEtype": mime,
            "dam:sha1": hashlib.sha1(data).hexdigest(), "dam:size": jcr.Long(len(data)),
            "dc:format": mime, "dc:title": asset.get("title", file_name)}
    size = image_size(data, suffix)
    if size:
        meta["tiff:ImageWidth"], meta["tiff:ImageLength"] = jcr.Long(size[0]), jcr.Long(size[1])

    content = jcr.Node("jcr:content", {"jcr:primaryType": "dam:AssetContent", "dam:assetState": "processed",
                                       "jcr:lastModified": now, "jcr:lastModifiedBy": "admin"},
                       [jcr.Node("metadata", meta), jcr.Node("related", {"jcr:primaryType": "nt:unstructured"})])
    asset_xml = jcr.document({"jcr:primaryType": "dam:Asset"}, [content])
    original_xml = jcr.document({"jcr:primaryType": "nt:file"},
                                [jcr.Node("jcr:content", {"jcr:mimeType": mime, "jcr:primaryType": "oak:Resource"})])

    base = f"jcr_root{project.dam_root.rstrip('/')}/{file_name}"
    return {
        f"{base}/.content.xml": asset_xml.encode(),
        f"{base}/_jcr_content/renditions/original": data,
        f"{base}/_jcr_content/renditions/original.dir/.content.xml": original_xml.encode(),
    }


def folder_entry(project, title, subpath=""):
    """sling:Folder node for the DAM root or one of its subfolders (e.g. "landing")."""
    xml = jcr.document({"jcr:primaryType": "sling:Folder"},
                       [jcr.Node("jcr:content", {"jcr:primaryType": "nt:unstructured", "jcr:title": title})])
    folder = project.dam_root.rstrip("/") + (f"/{subpath.strip('/')}" if subpath else "")
    return {f"jcr_root{folder}/.content.xml": xml.encode()}
