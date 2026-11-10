"""FileVault docview XML serialisation.

Only what the pipeline needs: typed property values, attribute escaping and a
small Node tree that renders the indented layout FileVault itself exports.
"""
from dataclasses import dataclass, field
from xml.sax.saxutils import escape

NAMESPACES = {
    "jcr": "http://www.jcp.org/jcr/1.0",
    "nt": "http://www.jcp.org/jcr/nt/1.0",
    "cq": "http://www.day.com/jcr/cq/1.0",
    "sling": "http://sling.apache.org/jcr/sling/1.0",
    "dam": "http://www.day.com/dam/1.0",
    "dc": "http://purl.org/dc/elements/1.1/",
    "tiff": "http://ns.adobe.com/tiff/1.0/",
    "oak": "http://jackrabbit.apache.org/oak/ns/1.0",
    "mix": "http://www.jcp.org/jcr/mix/1.0",
    "granite": "http://www.adobe.com/jcr/granite/1.0",
}

_ATTR_ENTITIES = {'"': "&quot;", "\n": "&#xa;", "\r": "&#xd;", "\t": "&#x9;"}
INDENT = "    "


class Long(int):
    """Marks an int that must be written as {Long}."""


class Date(str):
    """Marks an ISO-8601 string that must be written as {Date}."""


def format_value(value):
    """Return the docview string for a property value.

    Strings are untyped (String); bool → {Boolean}; Long → {Long};
    Date → {Date}; list → multi-value "[a,b]".
    """
    if isinstance(value, bool):
        return "{Boolean}" + ("true" if value else "false")
    if isinstance(value, Long):
        return "{Long}" + str(int(value))
    if isinstance(value, Date):
        return "{Date}" + str(value)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_escape_multi(str(v)) for v in value) + "]"
    if isinstance(value, int):
        raise TypeError(f"Ambiguous int {value!r}: wrap it in jcr.Long or pass a string")
    text = str(value)
    # A leading "{" or "[" would be read as a type hint or a multi-value.
    if text[:1] in ("{", "["):
        text = "\\" + text
    return text


def _escape_multi(item):
    return item.replace("\\", "\\\\").replace(",", "\\,")


def escape_attr(text):
    return escape(text, _ATTR_ENTITIES)


@dataclass
class Node:
    name: str
    props: dict = field(default_factory=dict)
    children: list = field(default_factory=list)

    def to_xml(self, depth=0):
        pad = INDENT * depth
        attrs = "".join(
            f"\n{pad}{INDENT}{key}=\"{escape_attr(format_value(value))}\""
            for key, value in self.props.items()
        )
        if not self.children:
            return f"{pad}<{self.name}{attrs}/>"
        inner = "\n".join(child.to_xml(depth + 1) for child in self.children)
        return f"{pad}<{self.name}{attrs}>\n{inner}\n{pad}</{self.name}>"


def namespace_decl(prefixes=None):
    used = prefixes or NAMESPACES.keys()
    return " ".join(f'xmlns:{p}="{NAMESPACES[p]}"' for p in used)


def document(root_props, children=(), prefixes=None):
    """Render a full .content.xml whose root node is jcr:root."""
    root = Node("jcr:root", dict(root_props), list(children))
    xml = root.to_xml()
    xml = xml.replace("<jcr:root", f"<jcr:root {namespace_decl(prefixes)}", 1)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml + "\n"


def vault_name(jcr_name):
    """Filesystem name FileVault uses for a JCR node name (cq:styleGroups → _cq_styleGroups)."""
    if ":" in jcr_name:
        prefix, local = jcr_name.split(":", 1)
        return f"_{prefix}_{local}"
    return jcr_name


def vault_path(jcr_path):
    return "/".join(vault_name(part) for part in jcr_path.split("/"))
