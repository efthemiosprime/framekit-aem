"""Preflight a built package against a TARGET AEM (e.g. the dev/stage author)
before installing it there. Read-only: only GETs Sling JSON.

Answers the questions that came up when moving a package from a local
author to a server:
  - do the component policies the style groups are written into exist?
  - do reused existing styles (class:… references) exist?
  - would any new style ID collide with a style already on the target?
  - do replaced pages exist, and are created pages really new?
  - do the header/footer experience fragments and the DAM parent exist?
"""
import re

from . import checks
from .mapping import style_index
from .net import HttpError
from .page import parent_path


def style_ids_in(xml):
    return {sid for group in re.findall(r'cq:styleIds="\[([^\]]*)\]"', xml) for sid in group.split(",") if sid}


def _exists(client, path):
    try:
        client.json(path, None)
        return True
    except HttpError:
        return False


def _descend(tree, rel_path):
    node = tree
    for part in rel_path.strip("/").split("/"):
        node = node.get(part) if isinstance(node, dict) else None
    return node


def run(client, project, build, ids, styles_spec):
    conf = project.aem["policiesRoot"].rstrip("/")
    try:
        target_policies = client.policies(conf)
    except HttpError as exc:
        return [(checks.ERROR, f"cannot read {conf} on the target: {exc}")]
    target_styles = style_index(target_policies)
    group, ours, findings = styles_spec["groupNode"], set(ids.values()), []

    for kind in styles_spec["styles"]:
        policy = project.component(kind)["policy"]
        if not isinstance(_descend(target_policies, policy), dict):
            findings.append((checks.ERROR, f"policy {policy} ({kind}) does not exist on the target"))

    for sid in sorted(ours & set(target_styles)):
        if target_styles[sid]["group"] != group:
            findings.append((checks.ERROR, f"style ID {sid} is already used on the target by "
                                           f".{target_styles[sid]['classes']} ({target_styles[sid]['policy']})"))

    used = set().union(*(style_ids_in(xml) for xml in build.page_xml.values())) if build.page_xml else set()
    for sid in sorted(used - ours - set(target_styles)):
        findings.append((checks.ERROR, f"pages use existing style {sid}, which the target does not have"))

    for spec in project.pages():
        path, mode = spec["path"], spec.get("mode", "replace")
        if mode == "replace" and not _exists(client, f"{path}/jcr:content"):
            findings.append((checks.ERROR, f"{path} does not exist on the target (mode replace)"))
        if mode == "create":
            if not _exists(client, f"{parent_path(path)}/jcr:content"):
                findings.append((checks.ERROR, f"parent of {path} does not exist on the target"))
            if _exists(client, f"{path}/jcr:content"):
                findings.append((checks.WARN, f"{path} already exists on the target and will be replaced"))

    fragments = {xf for xml in build.page_xml.values() for xf in re.findall(r'(?:headerXf|footerXf)="([^"]+)"', xml)}
    for xf in sorted(fragments):
        if not _exists(client, xf):
            findings.append((checks.ERROR, f"experience fragment {xf} does not exist on the target"))
    if not _exists(client, parent_path(project.dam_root)):
        findings.append((checks.ERROR, f"DAM parent {parent_path(project.dam_root)} does not exist on the target"))
    return findings
