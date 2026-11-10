"""Pre-package checks. Each returns a list of (level, message); level is
"error" (package must not be built) or "warn" (built, but someone should look).

These are the checks that caught real problems on the first production build:
  - an image referenced by a page but never added to the package,
  - style classes in LESS that authors could not select on their own,
  - page style references that resolve to nothing.
"""
import re
from pathlib import Path

ERROR, WARN = "error", "warn"


def asset_refs(page_xml, dam_root):
    """DAM paths (relative to dam_root) referenced anywhere in a page's XML."""
    root = re.escape(dam_root.rstrip("/") + "/")
    return set(re.findall(rf'{root}([^"\s<>]+)', page_xml))


def check_assets(page_xml_by_path, asset_files, dam_root):
    findings = []
    referenced = set()
    for path, xml in page_xml_by_path.items():
        refs = asset_refs(xml, dam_root)
        referenced |= refs
        for ref in sorted(refs - set(asset_files)):
            findings.append((ERROR, f"{path}: references {dam_root}/{ref}, which is not in the package"))
    for unused in sorted(set(asset_files) - referenced):
        findings.append((WARN, f"asset {unused} is packaged but no page references it"))
    return findings


def _less_classes(less_dir, prefix):
    """Author-facing classes: selectors starting with prefix, minus LESS mixins."""
    classes, mixins = set(), set()
    for path in sorted(Path(less_dir).glob(f"{prefix}*.less")):
        source = re.sub(r"//[^\n]*", "", path.read_text(encoding="utf-8"))
        mixins |= set(re.findall(rf"\.({re.escape(prefix)}[\w-]*)\s*\(", source))
        classes |= set(re.findall(rf"\.({re.escape(prefix)}[\w-]*)", source))
    return classes - mixins


def check_style_coverage(styles_spec, less_dir, prefix, js_classes=()):
    """Every author class in LESS is registered, and selectable on its own."""
    findings = []
    standalone, composite = set(), set()
    for entries in styles_spec["styles"].values():
        for entry in entries:
            parts = entry["classes"].split()
            (standalone if len(parts) == 1 else composite).update(parts if len(parts) > 1 else parts[:1])
    registered = standalone | composite
    if less_dir:
        defined = _less_classes(less_dir, prefix) - set(js_classes)
        for cls in sorted(defined - registered):
            findings.append((ERROR, f"class .{cls} is defined in LESS but not registered in any policy"))
        for cls in sorted(registered - defined - set(js_classes)):
            findings.append((WARN, f"class .{cls} is registered but has no rule in {less_dir}"))
    for cls in sorted(composite - standalone):
        findings.append((WARN, f"class .{cls} is only selectable inside a combined style"))
    return findings


def report(findings, out=print):
    errors = [m for level, m in findings if level == ERROR]
    for level, message in findings:
        out(f"  {'✗' if level == ERROR else '!'} {message}")
    return errors
