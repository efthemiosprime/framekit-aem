"""Command line entry point: python3 -m figma2aem <command> --project <dir>."""
import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from . import checks, clientlib, dam, designsystem, imaging, inventory, jcr, lessgen, mapping, page, preflight, styles, verify
from .aem_client import AemClient
from .config import ConfigError, Project, credentials, figma_token, load_json, require
from .figma_client import FigmaClient, crop_rect, fill_image
from .net import HttpError
from .package import write_package


# -- shared helpers ---------------------------------------------------------------------
def _aem(project):
    user, password = credentials("AEM")
    return AemClient(project.aem["baseUrl"], user, password)


def _figma(project):
    return FigmaClient(figma_token(), project.figma["fileKey"])


def _policies(project, args):
    if getattr(args, "policies_json", None):
        return load_json(args.policies_json)
    return _aem(project).policies(project.aem["policiesRoot"])


def _write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _style_ids(project, styles_spec, args, persist=True):
    styles.validate(styles_spec, project)
    policies = _policies(project, args)
    taken = set(mapping.style_index(policies))
    own = styles.own_group_ids(policies, project, styles_spec["groupNode"])
    lock_path = project.style_lock_path()
    ids = styles.assign_ids(styles_spec, styles.read_lock(lock_path), taken, own)
    if persist:
        styles.write_lock(lock_path, ids)
    return ids, len(taken)


# -- commands ----------------------------------------------------------------------------
def cmd_map(project, args):
    node_id = args.node or project.figma.get("pageNode")
    if not node_id:
        raise ConfigError("Pass --node or set figma.pageNode in project.json")
    payload = next(iter(_figma(project).nodes([node_id]).values()))
    inventory = mapping.figma_inventory(payload, project.figma.get("componentMap"))
    out = project.build_dir / "figma-inventory.json"
    _write(out, json.dumps(inventory, indent=2))
    print(mapping.inventory_markdown(inventory))
    unmapped = [g["component"] for g in inventory if not g["aemType"]]
    if unmapped:
        print(f"\nNot in figma.componentMap yet: {', '.join(unmapped)}")
    print(f"\nWrote {out}")


def cmd_aem_inventory(project, args):
    client = _aem(project)
    page_path = args.page or project.pages()[0]["path"]
    rows = mapping.aem_tree(client.page_content(page_path),
                            mapping.style_index(client.policies(project.aem["policiesRoot"])))
    out = project.build_dir / "aem-inventory.json"
    _write(out, json.dumps(rows, indent=2))
    print(mapping.aem_tree_text(rows))
    print(f"\nWrote {out}")


def cmd_styles(project, args):
    spec = project.styles()
    ids, taken = _style_ids(project, spec, args)
    for kind, entries in spec["styles"].items():
        for entry in entries:
            print(f"{ids[entry['key']]}  {kind:<10} {entry['classes']:<55} {entry['label']}")
    print(f"\n{len(ids)} styles; checked against {taken} existing AEM style IDs; lock: {project.style_lock_path()}")


def cmd_scaffold_less(project, args):
    spec = project.styles()
    # One synthetic tree holding every page body, so usages cover the whole project.
    page_spec = {"body": {"name": "pages", "type": "container", "children": [p["body"] for p in project.pages()]}}
    keys = [e["key"] for es in spec["styles"].values() for e in es] if args.all else args.key
    if not keys:
        raise ConfigError("Pass --key <style key> (repeatable) or --all")
    for key in keys:
        name, text = lessgen.scaffold(spec, page_spec, key)
        path, created = lessgen.write_scaffold(args.out, name, text)
        print(("created " if created else "exists, skipped ") + str(path))


def _design_snapshot(project):
    viewports = [(vp["figmaFrame"], vp["width"]) for p in project.pages()
                 for vp in p.get("verify", {}).get("viewports", []) if vp.get("figmaFrame")]
    extra = project.clientlib.get("figmaFrames", [])
    try:
        return designsystem.figma_snapshot(_figma(project), viewports, extra,
                                           project.clientlib.get("breakpoints"), http_error=HttpError)
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc


def cmd_clientlib(project, args):
    spec = clientlib.load_spec(project.clientlib, args.theme)
    styles_spec = project.styles()
    page_spec = {"body": {"name": "pages", "type": "container", "children": [p["body"] for p in project.pages()]}}
    out_dir = Path(args.out).expanduser() if args.out else project.clientlibs_dir
    snapshot_path = Path(args.snapshot).expanduser() if args.snapshot else project.build_dir / "figma-design-system.json"
    if args.figma:
        snapshot = _design_snapshot(project)
        _write(snapshot_path, json.dumps(snapshot, indent=1))
        print(f"Wrote {snapshot_path}" + (f"\n  ! variables: {snapshot['variablesError']}" if snapshot["variablesError"] else ""))
    snapshot = load_json(snapshot_path) if snapshot_path.exists() else None
    design = {**project.clientlib, "componentMap": project.figma.get("componentMap")}
    folder, results, report = clientlib.generate(spec, styles_spec, page_spec, out_dir, project.class_prefix,
                                                 snapshot=snapshot, design=design)
    for path, status in results:
        print(f"{status:<13} {path.relative_to(folder.parent)}")
    report_path = _write(project.build_dir / "design-system-report.md", report)
    print(f"\n{folder}  categories={','.join(spec.categories)}")
    print(report if snapshot else "No Figma snapshot: design-system/ holds empty defaults (run with --figma).")
    print(f"Report: {report_path}")
    if args.package:
        version = args.version or project.package.get("version", "1.0")
        name = f"{project.package['name']}-{spec.name}"
        out = write_package(project.build_dir / f"{name}-{version}.zip", name, project.package["group"], version,
                            f"Client library {spec.name} ({','.join(spec.categories)})",
                            [spec.jcr_path], clientlib.package_entries(spec, folder))
        print(f"{out}  (filter {spec.jcr_path})")


def cmd_export_assets(project, args):
    """figmaNode → rendered export (layer + children, at "scale");
    figmaFill → the original raster of the node's image fill (no children)."""
    assets = [a for a in _assets(project.pages())[0] if a.get("figmaNode") or a.get("figmaFill")]
    if not assets:
        raise ConfigError("No assets with figmaNode/figmaFill in page.json")
    client = _figma(project)
    todo = [a for a in assets if args.force or not (project.assets_dir / a["file"]).exists()]
    for asset in assets:
        if asset not in todo:
            print(f"exists, skipped {project.assets_dir / asset['file']} (use --force)")

    urls = {}
    renders = [a for a in todo if a.get("figmaNode")]
    by_scale = {}
    for asset in renders:
        by_scale.setdefault((asset.get("scale", 2), Path(asset["file"]).suffix.lstrip(".") or "png"), []).append(asset)
    for (scale, fmt), group in by_scale.items():
        rendered = client.image_urls([a["figmaNode"] for a in group], fmt=fmt, scale=scale)
        for asset in group:
            urls[asset["file"]] = (rendered[asset["figmaNode"].replace("-", ":")], f"{scale}x render")
    fills = [a for a in todo if a.get("figmaFill")]
    crops = {}
    if fills:
        fill_urls = client.image_fill_urls()
        docs = client.nodes([a["figmaFill"] for a in fills], depth=0)
        for asset in fills:
            doc = docs[asset["figmaFill"].replace("-", ":")]["document"]
            ref, transform = fill_image(doc)
            if ref not in fill_urls:
                raise HttpError(f"Figma returned no URL for image fill {ref} ({asset['file']})")
            # "crop": true applies the layer's Figma crop (what the design shows) to the original.
            if asset.get("crop") and transform:
                crops[asset["file"]] = transform
            urls[asset["file"]] = (fill_urls[ref], "cropped fill" if asset["file"] in crops else "original fill")

    for asset in todo:
        url, kind = urls[asset["file"]]
        target = project.assets_dir / asset["file"]
        target.parent.mkdir(parents=True, exist_ok=True)
        data = client.download(url)
        if not data:
            raise HttpError(f"Empty download for {asset['file']}")
        target.write_bytes(data)
        if asset["file"] in crops:
            raw = target.with_name(target.stem + ".original" + target.suffix)
            target.rename(raw)
            rect = crop_rect(crops[asset["file"]], *imaging.size(raw))
            imaging.crop(raw, target, rect, asset.get("width"))
            raw.unlink()
            print(f"wrote {target} (crop {rect}{', width ' + str(asset['width']) if asset.get('width') else ''})")
            continue
        print(f"wrote {target} ({len(data)} bytes, {kind})")


@dataclass
class Build:
    entries: dict
    filters: list
    rollback_entries: dict
    rollback_filters: list
    page_xml: dict
    findings: list
    style_count: int
    aem_style_ids: int
    ids: dict
    styles_spec: dict


def _assets(page_specs):
    """Union of all pages' assets, by DAM file path (first title wins, conflicts reported)."""
    merged, findings = {}, []
    for spec in page_specs:
        for asset in spec.get("assets", []):
            file = asset["file"]
            if file in merged and merged[file].get("title") != asset.get("title"):
                findings.append((checks.WARN, f"asset {file} has different titles in two page files"))
            merged.setdefault(file, asset)
    return list(merged.values()), findings


def _render(project, spec, ids, existing, parents):
    """(page XML, package filter root, rollback entry or None) for one page spec."""
    body = page.build_body(require(spec, "body", spec["_file"]), project, ids, existing=existing)
    path = require(spec, "path", spec["_file"])
    mode = spec.get("mode", "replace")
    if mode == "replace":
        base = page.page_xml_from_package(project.path(require(spec, "basePackage", spec["_file"])), path)
        xml = page.render_page(base, body, project.aem.get("requiredPageProps", ["cq:template="]))
        return xml, f"{path}/jcr:content", base
    if mode == "create":
        parent = page.parent_path(path)
        if parent not in parents:
            parents[parent] = spec.get("parentProps") or _aem(project).json(f"{parent}/jcr:content", None)
        return page.render_new_page(spec, parents[parent], body), path, None
    raise ConfigError(f"{spec['_file']}: mode must be 'replace' or 'create', not {mode!r}")


def _build(project, args, persist_ids=True):
    spec = project.styles()
    styles.validate(spec, project)
    policies = _policies(project, args)
    existing = mapping.style_index(policies)
    own = styles.own_group_ids(policies, project, spec["groupNode"])
    lock_path = project.style_lock_path()
    ids = styles.assign_ids(spec, styles.read_lock(lock_path), set(existing), own)
    if persist_ids:
        styles.write_lock(lock_path, ids)

    entries, filters, rb_entries, rb_filters, page_xml, parents = {}, [], {}, [], {}, {}
    for page_spec in project.pages():
        xml, root, base = _render(project, page_spec, ids, existing, parents)
        entry = f"jcr_root{jcr.vault_path(page_spec['path'])}/.content.xml"
        entries[entry] = xml.encode("utf-8")
        page_xml[page_spec["path"]] = xml
        filters.append(root)
        rb_filters.append(root)
        if base is not None:           # replaced page: restore its original body
            rb_entries[entry] = base.encode("utf-8")
        # created page: filter with no content → the rollback deletes it

    assets, findings = _assets(project.pages())
    if assets:
        entries.update(dam.folder_entry(project, project.package.get("damFolderTitle", project.package["name"])))
        for sub in sorted({str(Path(a["file"]).parent) for a in assets} - {"."}):
            title = project.data.get("damFolders", {}).get(sub, sub.split("/")[-1])
            entries.update(dam.folder_entry(project, title, sub))
        for asset in assets:
            entries.update(dam.asset_entries(asset, project))
        filters.append(project.dam_root)

    style_entries, style_filters = styles.package_entries(spec, ids, project)
    entries.update(style_entries)
    filters += style_filters

    findings += checks.check_assets(page_xml, [a["file"] for a in assets], project.dam_root)
    findings += checks.check_style_coverage(spec, project.less_dir, project.class_prefix,
                                            project.data.get("jsClasses", []))
    used = {sid for xml in page_xml.values()
            for group in re.findall(r'cq:styleIds="\[([^\]]*)\]"', xml) for sid in group.split(",") if sid}
    reused = sorted(used & (set(existing) - set(ids.values())))
    for sid in reused:
        findings.append((checks.WARN, f"reuses existing style {sid} (.{existing[sid]['classes']}); it must exist on the target AEM"))
    return Build(entries, filters, rb_entries, rb_filters, page_xml, findings, len(ids), len(existing), ids, spec)


def cmd_check(project, args):
    build = _build(project, args, persist_ids=False)
    print(f"{len(build.page_xml)} page(s), {build.style_count} styles, {len(build.entries)} package files")
    errors = checks.report(build.findings)
    if errors:
        raise ConfigError(f"{len(errors)} check(s) failed")
    print("checks passed" + (" (with warnings)" if build.findings else ""))


def cmd_page(project, args):
    build = _build(project, args, persist_ids=False)
    for path, xml in build.page_xml.items():
        out = _write(project.build_dir / "pages" / (path.strip("/").replace("/", "_") + ".content.xml"), xml)
        print(f"Wrote {out}")


def cmd_package(project, args):
    pkg = project.package
    build = _build(project, args)
    errors = checks.report(build.findings)
    if errors:
        raise ConfigError(f"{len(errors)} check(s) failed; package not written")

    version = args.version or pkg.get("version", "1.0")
    out = write_package(project.build_dir / f"{pkg['name']}-{version}.zip", pkg["name"], pkg["group"], version,
                        pkg.get("description", "Generated by figma2aem"), build.filters, build.entries)
    extra = [f for f in build.filters if f not in build.rollback_filters] if args.rollback_all else []
    rollback = write_package(project.build_dir / f"{pkg['name']}-rollback-{version}.zip",
                             f"{pkg['name']}-rollback", pkg["group"], version,
                             "Restores replaced pages, deletes created pages"
                             + ("; removes generated style groups and DAM folder" if extra else ""),
                             build.rollback_filters + extra, build.rollback_entries)

    print(f"{out}  ({out.stat().st_size} bytes, {len(build.entries)} files, {len(build.page_xml)} page(s))")
    print(f"{rollback}  ({'pages + styles + DAM' if extra else 'pages only'})")
    print("Filters:\n  " + "\n  ".join(build.filters))
    print(f"{build.style_count} styles; IDs checked against {build.aem_style_ids} existing AEM IDs.")


def cmd_preflight(project, args):
    """Check a TARGET AEM (read-only) for everything the package relies on but does not contain."""
    build = _build(project, args, persist_ids=False)
    user, password = credentials(args.target_env)
    target = AemClient(args.target, user, password)
    findings = preflight.run(target, project, build, build.ids, build.styles_spec)
    print(f"Target {args.target}: {len(build.page_xml)} page(s), {build.style_count} styles")
    errors = checks.report(findings)
    if errors:
        raise ConfigError(f"{len(errors)} preflight check(s) failed; do not install on {args.target}")
    print("preflight passed" + (" (with warnings)" if findings else ""))


def cmd_inventory(project, args):
    """Placeable components + every existing style with its page usage (the "map before make" data)."""
    client = _aem(project)
    rows = inventory.collect(client, project)
    out = _write(project.build_dir / "aem-styles-inventory.json", json.dumps(rows, indent=2))
    print(inventory.markdown(rows))
    print(f"\nWrote {out}")


def cmd_verify_spec(project, args):
    client = _figma(project)
    for page_spec in project.pages():
        if "verify" not in page_spec:
            continue
        frames = [vp["figmaFrame"] for vp in page_spec["verify"]["viewports"]]
        spec = verify.build_spec(page_spec, client.nodes(frames))
        name = page_spec["path"].strip("/").replace("/", "_")
        out = _write(project.build_dir / f"verify-{name}.json", json.dumps(spec, indent=2))
        counts = ", ".join(f"{vp['width']}px: {len(vp['checks'])}" for vp in spec["viewports"])
        print(f"Wrote {out} ({counts} checks)\nRun: node verify/probe.mjs {out}")


def cmd_backup(project, args):
    if not args.yes:
        raise ConfigError("backup creates and builds a package in AEM /etc/packages; re-run with --yes")
    pkg = project.package
    name = f"{pkg['name']}-backup"
    roots = [f"{s['path']}/jcr:content" if s.get("mode", "replace") == "replace" else s["path"]
             for s in project.pages()]
    data = _aem(project).backup_package(pkg["group"], name, args.version, roots)
    out = project.build_dir / f"{name}-{args.version}.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    print(f"Wrote {out}; set page basePackage to it to build from this snapshot")


COMMANDS = {
    "map": (cmd_map, "Figma page → component/variant inventory"),
    "aem-inventory": (cmd_aem_inventory, "AEM page → component tree with resolved style classes"),
    "styles": (cmd_styles, "Assign/lock Style System IDs and list them"),
    "scaffold-less": (cmd_scaffold_less, "Write starter LESS files for styles"),
    "clientlib": (cmd_clientlib, "Write clientlib-<theme> (LESS/JS skeleton + component styles)"),
    "export-assets": (cmd_export_assets, "Export page.json assets from Figma"),
    "check": (cmd_check, "Run the pre-package checks (assets, styles, LESS coverage)"),
    "page": (cmd_page, "Render every page's XML to build/pages/"),
    "package": (cmd_package, "Build install + rollback packages"),
    "preflight": (cmd_preflight, "Check a target AEM for what the package relies on (read-only)"),
    "inventory": (cmd_inventory, "List placeable components and existing styles with page usage"),
    "verify-spec": (cmd_verify_spec, "Build the Figma geometry spec for verify/probe.mjs"),
    "backup": (cmd_backup, "Snapshot the page via AEM Package Manager (writes to AEM)"),
}


def parser():
    p = argparse.ArgumentParser(prog="figma2aem", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    for name, (_, help_text) in COMMANDS.items():
        s = sub.add_parser(name, help=help_text)
        s.add_argument("--project", required=True, help="Project folder containing project.json")
        if name in ("styles", "check", "page", "package", "preflight"):
            s.add_argument("--policies-json", help="Use a saved policies.infinity.json instead of live AEM")
        if name == "map":
            s.add_argument("--node", help="Figma node id of the page frame")
        if name == "aem-inventory":
            s.add_argument("--page", help="AEM page path (defaults to page.json path)")
        if name == "scaffold-less":
            s.add_argument("--key", action="append", help="Style key (repeatable)")
            s.add_argument("--all", action="store_true")
            s.add_argument("--out", required=True, help="Directory for the LESS files")
        if name == "clientlib":
            s.add_argument("--theme", help="Theme name → clientlib-<theme> (default: project.json clientlib.theme)")
            s.add_argument("--out", help="Folder that receives clientlib-<theme>/ (default: clientlib.dir or build/clientlibs)")
            s.add_argument("--package", action="store_true", help="Also write an /apps package zip (needs clientlib.appsPath)")
            s.add_argument("--figma", action="store_true",
                           help="Fetch variables, styles, grids, fonts, variants from Figma into the snapshot first")
            s.add_argument("--snapshot", help="Snapshot file (default build/figma-design-system.json)")
            s.add_argument("--version")
        if name == "export-assets":
            s.add_argument("--force", action="store_true", help="Overwrite existing files")
        if name == "package":
            s.add_argument("--version")
            s.add_argument("--rollback-all", action="store_true",
                           help="Rollback also deletes the generated style groups and DAM folder")
        if name == "preflight":
            s.add_argument("--target", required=True, help="Target author base URL, e.g. https://author-dev.example.com")
            s.add_argument("--target-env", default="TARGET_AEM",
                           help="Env prefix for target credentials (<PREFIX>_USER / <PREFIX>_PASSWORD)")
        if name == "backup":
            s.add_argument("--version", default="1.0")
            s.add_argument("--yes", action="store_true", help="Confirm writing to AEM /etc/packages")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        project = Project.load(args.project)
        COMMANDS[args.command][0](project, args)
    except (ConfigError, HttpError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0
