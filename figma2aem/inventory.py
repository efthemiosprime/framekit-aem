"""What already exists in AEM, so a design is mapped onto it before anything new
is created ("map before you make"). Read-only.

project.json → "aem": {"template": "/conf/<site>/settings/wcm/templates/content-page",
                        "contentRoot": "/content/<site>"}
"""
import json
import urllib.parse
from collections import defaultdict

from .config import require
from .mapping import style_index


def _query(client, params):
    query = urllib.parse.urlencode({**params, "p.limit": "-1", "p.hits": "selective"})
    raw = client._fetch(f"{client.base_url}/bin/querybuilder.json?{query}", headers=client._headers)
    return json.loads(raw).get("hits", [])


def placeable_components(client, project):
    """Components allowed in the template's main container, resolved to paths/titles."""
    template = require(project.aem, "template", "project.json aem")
    mapping = client.json(f"{template}/policies")
    policy_ref = (mapping.get("jcr:content", {}).get("root", {}).get("container", {}) or {}).get("cq:policy")
    if not policy_ref:
        return {"allowed": [], "components": []}
    policy = client.json(f"{project.aem['policiesRoot'].rstrip('/')}/{policy_ref}")
    allowed = policy.get("components", [])
    allowed = [allowed] if isinstance(allowed, str) else allowed
    groups = {a[len("group:"):] for a in allowed if a.startswith("group:")}
    paths = {a for a in allowed if not a.startswith("group:")}
    hits = _query(client, {"path": "/apps", "type": "cq:Component",
                           "p.properties": "jcr:path jcr:title componentGroup sling:resourceSuperType"})
    components = [h for h in hits if h.get("componentGroup") in groups or h["jcr:path"] in paths]
    return {"allowed": allowed, "components": sorted(components, key=lambda h: h["jcr:path"])}


def style_usage(client, project):
    """{styleId: set(page paths)} for every page under contentRoot."""
    root = require(project.aem, "contentRoot", "project.json aem")
    usage = defaultdict(set)
    for hit in _query(client, {"path": root, "property": "cq:styleIds", "property.operation": "exists",
                               "p.properties": "jcr:path cq:styleIds"}):
        page = hit["jcr:path"].split("/jcr:content")[0]
        ids = hit.get("cq:styleIds") or []
        for sid in ([ids] if isinstance(ids, str) else ids):
            if sid:
                usage[str(sid)].add(page)
    return usage


def collect(client, project):
    styles = style_index(client.policies(project.aem["policiesRoot"]))
    usage = style_usage(client, project)
    return {
        "placeable": placeable_components(client, project),
        "styles": [{"id": sid, **info, "pages": sorted(usage.get(sid, ()))} for sid, info in sorted(styles.items())],
    }


def markdown(rows):
    lines = ["## Placeable components", "", "| Component | Group | Base |", "|---|---|---|"]
    for c in rows["placeable"]["components"]:
        lines.append(f"| {c.get('jcr:title', '')} (`{c['jcr:path']}`) | {c.get('componentGroup', '')} | "
                     f"{c.get('sling:resourceSuperType', '')} |")
    by_policy = defaultdict(list)
    for s in rows["styles"]:
        by_policy[s["policy"]].append(s)
    lines += ["", "## Existing styles (° = used on no page)", ""]
    for policy, items in sorted(by_policy.items()):
        lines.append(f"**{policy}** ({len(items)})")
        lines.append("  " + " · ".join(f"`{s['classes']}`{'' if s['pages'] else '°'}" for s in items))
    return "\n".join(lines)
