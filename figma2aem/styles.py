"""Style System groups: stable IDs + policy docview XML + package filters.

styles.json
-----------
{
  "groupLabel": "Design System",        label shown in the Styles dropdown
  "groupNode":  "designsystem",          node name under cq:styleGroups (one per policy)
  "idBase":     1794500000000,      first ID to try for new styles
  "styles": {
    "container": [ {"key": "section", "classes": "ds-section", "label": "DS Section"}, ... ],
    "text":      [ ... ]
  }
}

Keys under "styles" are component types from project.json; each type's
"policy" says which policy receives the group.

IDs are written to a lock file the first time a key is seen and reused on
every later run, so re-building never re-numbers styles that pages already
reference. New IDs avoid every ID already present in AEM (except those in our
own group, which are ours to reuse).
"""
import json

from . import jcr
from .config import ConfigError, require


def validate(styles_spec, project):
    require(styles_spec, "groupNode", "styles.json")
    require(styles_spec, "groupLabel", "styles.json")
    seen = set()
    for kind, entries in require(styles_spec, "styles", "styles.json").items():
        comp = project.component(kind)
        if "policy" not in comp:
            raise ConfigError(f"Component type '{kind}' has styles but no 'policy' in project.json")
        for entry in entries:
            for key in ("key", "classes", "label"):
                require(entry, key, f"styles.json {kind}")
            if entry["key"] in seen:
                raise ConfigError(f"Duplicate style key '{entry['key']}' in styles.json")
            seen.add(entry["key"])


def own_group_ids(policies_json, project, group_node):
    """IDs already living in our own style group nodes in AEM."""
    ids = set()
    for comp in project.components.values():
        node = _descend(policies_json, comp.get("policy", ""))
        group = (node or {}).get("cq:styleGroups", {}).get(group_node, {})
        for style in group.get("cq:styles", {}).values():
            if isinstance(style, dict) and "cq:styleId" in style:
                ids.add(str(style["cq:styleId"]))
    return ids


def _descend(tree, rel_path):
    node = tree
    for part in [p for p in rel_path.split("/") if p]:
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def assign_ids(styles_spec, lock, taken_in_aem, own_ids=frozenset()):
    """Return {key: id}. Reuses lock entries; new IDs avoid AEM and lock IDs."""
    blocked = (set(taken_in_aem) - set(own_ids)) | set(lock.values())
    result, next_id = {}, int(styles_spec.get("idBase", 1794500000000))
    for entries in styles_spec["styles"].values():
        for entry in entries:
            key = entry["key"]
            if key in lock:
                if lock[key] in set(taken_in_aem) - set(own_ids):
                    raise ConfigError(f"Locked ID {lock[key]} for '{key}' now belongs to another AEM style")
                result[key] = lock[key]
                continue
            while str(next_id) in blocked:
                next_id += 1
            result[key] = str(next_id)
            blocked.add(str(next_id))
    return result


def group_xml(entries, ids, label):
    items = [jcr.Node(f"item{i}", {"jcr:primaryType": "nt:unstructured",
                                    "cq:styleClasses": e["classes"],
                                    "cq:styleId": ids[e["key"]],
                                    "cq:styleLabel": e["label"]})
             for i, e in enumerate(entries)]
    styles = jcr.Node("cq:styles", {"jcr:primaryType": "nt:unstructured"}, items)
    return jcr.document({"jcr:primaryType": "nt:unstructured",
                         "cq:styleGroupLabel": label,
                         "cq:styleGroupMultiple": "true"}, [styles], prefixes=("jcr", "nt", "cq"))


def package_entries(styles_spec, ids, project):
    """{zip path: bytes} and filter roots for every style group."""
    conf_root = require(project.aem, "policiesRoot", "project.json aem").rstrip("/")
    entries, filters = {}, []
    for kind, group in styles_spec["styles"].items():
        policy = project.component(kind)["policy"].strip("/")
        jcr_path = f"{conf_root}/{policy}/cq:styleGroups/{styles_spec['groupNode']}"
        entries[f"jcr_root{jcr.vault_path(jcr_path)}/.content.xml"] = group_xml(group, ids, styles_spec["groupLabel"]).encode()
        filters.append(jcr_path)
    return entries, filters


def classes_by_key(styles_spec):
    return {e["key"]: e["classes"] for entries in styles_spec["styles"].values() for e in entries}


def read_lock(path):
    return json.loads(path.read_text()) if path.exists() else {}


def write_lock(path, ids):
    path.write_text(json.dumps(dict(sorted(ids.items())), indent=2) + "\n")
