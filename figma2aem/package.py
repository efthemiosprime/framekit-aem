"""FileVault package zips (filter.xml + properties.xml + jcr_root)."""
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from . import jcr


def filter_xml(roots):
    """roots: list of str or (root, mode)."""
    lines = []
    for item in roots:
        root, mode = (item, None) if isinstance(item, str) else item
        mode_attr = f' mode="{mode}"' if mode else ""
        lines.append(f'    <filter root="{jcr.escape_attr(root)}"{mode_attr}/>')
    return '<?xml version="1.0" encoding="UTF-8"?>\n<workspaceFilter version="1.0">\n' + "\n".join(lines) + "\n</workspaceFilter>\n"


def properties_xml(name, group, version, description):
    return ('<?xml version="1.0" encoding="utf-8" standalone="no"?>\n'
            '<!DOCTYPE properties SYSTEM "http://java.sun.com/dtd/properties.dtd">\n<properties>\n'
            f'<entry key="name">{escape(name)}</entry>\n'
            f'<entry key="group">{escape(group)}</entry>\n'
            f'<entry key="version">{escape(version)}</entry>\n'
            f'<entry key="description">{escape(description)}</entry>\n'
            '<entry key="requiresRoot">false</entry>\n</properties>\n')


def write_package(path, name, group, version, description, filters, entries):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    files = {
        "META-INF/vault/filter.xml": filter_xml(filters).encode(),
        "META-INF/vault/properties.xml": properties_xml(name, group, version, description).encode(),
        **entries,
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for entry in sorted(files):
            zf.writestr(entry, files[entry])
    return path
