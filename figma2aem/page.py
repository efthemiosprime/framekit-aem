"""page.json → jcr:content docview XML.

page.json
---------
{
  "path": "/content/site/us/en",            target page (only its jcr:content is replaced)
  "basePackage": "path/to/export.zip",       package containing the current page XML; its
                                              jcr:content properties (template, XFs, GTM…) are kept
  "body": { component node },               the new root node (usually "root")
  "assets": [ ... ],                         see dam.py
  "verify": { ... }                          see verify.py
}

Component node:
{
  "name": "card_feature",                  JCR node name (unique among siblings)
  "type": "teaser",                         key in project.json "components"
  "styles": ["teaser_card"],                keys from styles.json → cq:styleIds
  "props": { "jcr:title": "<p>…</p>", "fileReference": "dam:card.png" },
  "actions": [ {"link": "/content/…", "text": "Read more"} ],   teaser call-to-actions
  "children": [ ...component nodes... ],
  "verify": { "figma": "Feature card", "selector": ".ds-card .cmp-teaser" }
}

Prop values starting with "dam:" expand to <project damRoot>/<rest>.
Component "defaults" from project.json are applied under the node's props.
"""
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from . import jcr
from .config import ConfigError, require

DAM_PREFIX = "dam:"


CLASS_PREFIX = "class:"


def resolve_style(ref, kind, project, style_ids, existing, where):
    """A styles.json key, or "class:<cq:styleClasses>" for a style that already
    exists in the component's AEM policy (reuse without re-registering it)."""
    if not ref.startswith(CLASS_PREFIX):
        if ref not in style_ids:
            raise ConfigError(f"{where}: unknown style key '{ref}' (not in styles.json)")
        return style_ids[ref]
    wanted = ref[len(CLASS_PREFIX):].strip()
    policy = project.component(kind).get("policy", "").strip("/")
    matches = [sid for sid, info in (existing or {}).items()
               if info["classes"].strip() == wanted and info["policy"].endswith(policy)]
    if len(matches) != 1:
        found = "no" if not matches else f"{len(matches)}"
        raise ConfigError(f"{where}: {found} existing style with classes '{wanted}' on policy {policy or '?'}")
    return matches[0]


def build_body(node_spec, project, style_ids, path="body", existing=None):
    name = require(node_spec, "name", path)
    kind = require(node_spec, "type", f"{path}.{name}")
    comp = project.component(kind)
    where = f"{path}.{name}"

    props = {"jcr:primaryType": "nt:unstructured", "sling:resourceType": comp["resourceType"]}
    styles = node_spec.get("styles", [])
    if styles:
        props["cq:styleIds"] = [resolve_style(s, kind, project, style_ids, existing, where) for s in styles]
    for key, value in {**comp.get("defaults", {}), **node_spec.get("props", {})}.items():
        props[key] = _expand(value, project)

    children = []
    if node_spec.get("actions"):
        children.append(_actions(node_spec["actions"], project))
    for child in node_spec.get("children", []):
        children.append(build_body(child, project, style_ids, where, existing))
    _check_unique_names(children, where)
    return jcr.Node(name, props, children)


def _expand(value, project):
    if isinstance(value, str) and value.startswith(DAM_PREFIX):
        return f"{project.dam_root.rstrip('/')}/{value[len(DAM_PREFIX):]}"
    if isinstance(value, list):
        return [_expand(v, project) for v in value]
    return value


def _actions(actions, project):
    items = []
    for i, action in enumerate(actions):
        require(action, "link", "actions")
        items.append(jcr.Node(f"item{i}", {"jcr:primaryType": "nt:unstructured",
                                            "link": _expand(action["link"], project),
                                            "text": action.get("text", ""),
                                            "openInNewTab": action.get("openInNewTab", "false")}))
    return jcr.Node("actions", {"jcr:primaryType": "nt:unstructured"}, items)


def _check_unique_names(children, where):
    names = [c.name for c in children]
    dupes = {n for n in names if names.count(n) > 1}
    if dupes:
        raise ConfigError(f"{where}: duplicate child names {sorted(dupes)}")


# -- page XML ------------------------------------------------------------------------
def page_xml_from_package(package_zip, page_path):
    """Return the current page's .content.xml text from an exported package."""
    entry = f"jcr_root{jcr.vault_path(page_path)}/.content.xml"
    try:
        with zipfile.ZipFile(Path(package_zip).expanduser()) as zf:
            return zf.read(entry).decode("utf-8")
    except KeyError as exc:
        raise ConfigError(f"{package_zip} has no {entry}") from exc
    except FileNotFoundError as exc:
        raise ConfigError(f"Base package not found: {package_zip}") from exc


def split_page_xml(xml):
    """(jcr:root open tag, jcr:content open tag without '>') from a page .content.xml."""
    match = re.search(r"(<jcr:root\b[^>]*>)\s*(<jcr:content\b[^>]*?)/?>", xml, re.S)
    if not match:
        raise ConfigError("Page XML has no <jcr:content> element")
    return match.group(1), match.group(2)


def render_page(base_xml, body_node, required_props=("cq:template=",), modified_by="admin"):
    root_open, content_open = split_page_xml(base_xml)
    for prop in required_props:
        if prop not in content_open:
            raise ConfigError(f"Current page jcr:content is missing {prop!r}; refusing to build")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    content_open = re.sub(r'cq:lastModified="[^"]*"', f'cq:lastModified="{{Date}}{now}"', content_open)
    content_open = re.sub(r'cq:lastModifiedBy="[^"]*"', f'cq:lastModifiedBy="{modified_by}"', content_open)
    body = body_node.to_xml(depth=2)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            f"{root_open}\n    {content_open}>\n{body}\n    </jcr:content>\n</jcr:root>\n")


def walk_spec(node_spec):
    yield node_spec
    for child in node_spec.get("children", []):
        yield from walk_spec(child)


# -- new pages ("mode": "create") ------------------------------------------------------
# Properties copied from the parent page's jcr:content unless page.json lists its own
# "inheritProps". Timestamps, replication state and versioning are never copied.
DEFAULT_INHERIT = ["cq:template", "headerXf", "footerXf", "website", "gtmId", "nonProdGTMId",
                   "googleverificationcode", "bingverificationcode", "socialMedia", "pwaCachestrategy",
                   "pwaDisplay", "pwaOrientation", "disableOktaAuthentication", "enableGoogleMapsApiKey",
                   "hideInSearch"]


def inherited_props(parent_content, names):
    """Typed copies of parent jcr:content properties (Sling JSON → docview types)."""
    props = {}
    for name in names:
        if name not in parent_content:
            continue
        value = parent_content[name]
        if isinstance(value, bool) or isinstance(value, (list, str)):
            props[name] = value
        elif isinstance(value, int):
            props[name] = jcr.Long(value)
        else:
            raise ConfigError(f"Cannot copy parent property {name}={value!r}")
    return props


def render_new_page(page_spec, parent_content, body_node, modified_by="admin"):
    inherit = page_spec.get("inheritProps", DEFAULT_INHERIT)
    props = {"jcr:primaryType": "cq:PageContent",
             "sling:resourceType": page_spec.get("pageResourceType", parent_content.get("sling:resourceType", ""))}
    props.update(inherited_props(parent_content, inherit))
    for required in ("cq:template", "sling:resourceType"):
        if not props.get(required):
            raise ConfigError(f"{page_spec.get('path')}: no {required} (set it in pageProps or inherit it)")
    props.update(page_spec.get("pageProps", {}))
    props["cq:lastModified"] = jcr.Date(datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"))
    props["cq:lastModifiedBy"] = modified_by
    content = jcr.Node("jcr:content", props, [body_node])
    return jcr.document({"jcr:primaryType": "cq:Page"}, [content])


def parent_path(page_path):
    return page_path.rsplit("/", 1)[0]
