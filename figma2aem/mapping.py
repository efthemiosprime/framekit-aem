"""Inventories: which Figma components/variants a page uses, and how an AEM
page is built (resource types + resolved Style System classes).

Both are pure functions over already-fetched JSON so they can be tested
without network access.
"""
from collections import OrderedDict

from .figma_client import walk


# -- Figma ------------------------------------------------------------------------
def figma_inventory(node_payload, component_map=None):
    """Group the outermost instances of a Figma page by component.

    node_payload: one entry of FigmaClient.nodes() → {"document", "components", "componentSets"}.
    component_map: optional {figma component(set) name: AEM component type}.
    Returns an ordered list of dicts (one per component / component set).
    """
    components = node_payload.get("components", {})
    sets = node_payload.get("componentSets", {})
    component_map = component_map or {}
    groups = OrderedDict()

    for node, inside_instance in walk(node_payload["document"]):
        if node.get("type") != "INSTANCE" or inside_instance:
            continue
        meta = components.get(node.get("componentId"), {})
        set_meta = sets.get(meta.get("componentSetId"), {})
        name = set_meta.get("name") or meta.get("name") or node.get("name")
        group = groups.setdefault(name, {
            "component": name,
            "isVariantSet": bool(set_meta),
            "remote": meta.get("remote", False),
            "aemType": component_map.get(name),
            "variants": OrderedDict(),
        })
        variant = _variant_label(node)
        entry = group["variants"].setdefault(variant, {"count": 0, "hidden": 0, "nodeIds": []})
        entry["count"] += 1
        entry["hidden"] += 0 if node.get("visible", True) else 1
        entry["nodeIds"].append(node["id"])

    return [dict(g, variants=dict(g["variants"])) for g in groups.values()]


def _variant_label(instance):
    props = instance.get("componentProperties") or {}
    variants = [f"{k}={v.get('value')}" for k, v in props.items() if v.get("type") == "VARIANT"]
    return ", ".join(variants) if variants else "(no variants)"


def inventory_markdown(inventory):
    lines = ["| Figma component | AEM type | Variant used | Count |", "|---|---|---|---|"]
    for group in inventory:
        for variant, info in group["variants"].items():
            hidden = f" ({info['hidden']} hidden)" if info["hidden"] else ""
            lines.append(f"| {group['component']} | {group['aemType'] or '—'} | {variant} | {info['count']}{hidden} |")
    return "\n".join(lines)


# -- AEM --------------------------------------------------------------------------
def style_index(policies_json):
    """{styleId: {"classes", "label", "policy"}} from a policies.infinity.json tree."""
    index = {}

    def visit(node, path):
        for key, value in node.items():
            if not isinstance(value, dict):
                continue
            child = f"{path}/{key}"
            if "cq:styleId" in value:
                group = child.split("/cq:styleGroups/")[1].split("/")[0] if "/cq:styleGroups/" in child else ""
                index[str(value["cq:styleId"])] = {
                    "classes": value.get("cq:styleClasses", ""),
                    "label": value.get("cq:styleLabel", ""),
                    "policy": child.split("/cq:styleGroups")[0].lstrip("/"),
                    "group": group,
                }
            visit(value, child)

    visit(policies_json, "")
    return index


def aem_tree(content_json, styles_by_id):
    """Flatten a page's jcr:content into rows: depth, node name, resource type, classes."""
    rows = []

    def visit(node, name, depth):
        if not isinstance(node, dict):
            return
        rtype = node.get("sling:resourceType")
        if rtype:
            ids = [i for i in _as_list(node.get("cq:styleIds")) if i]
            classes = [styles_by_id.get(str(i), {}).get("classes", f"?{i}") for i in ids]
            rows.append({"depth": depth, "name": name, "resourceType": rtype,
                         "styleIds": ids, "classes": " ".join(c for c in classes if c).strip()})
        for key, value in node.items():
            if isinstance(value, dict) and not key.startswith("cq:responsive"):
                visit(value, key, depth + (1 if rtype else 0))

    for key, value in content_json.items():
        if isinstance(value, dict):
            visit(value, key, 0)
    return rows


def _as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def aem_tree_text(rows):
    return "\n".join(
        f"{'  ' * r['depth']}{r['name']} [{r['resourceType'].split('/')[-1]}]" + (f"  .{r['classes'].replace(' ', '.')}" if r["classes"] else "")
        for r in rows)
