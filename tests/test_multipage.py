"""Offline tests for multi-page builds, new pages, checks, crops and preflight."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from figma2aem import checks, jcr, page, preflight
from figma2aem.config import ConfigError, Project
from figma2aem.figma_client import crop_rect
from figma2aem.net import HttpError

PARENT = {"jcr:primaryType": "cq:PageContent", "sling:resourceType": "site/components/page",
          "cq:template": "/conf/site/settings/wcm/templates/content-page", "headerXf": "/content/xf/header",
          "socialMedia": ["facebook"], "hideInSearch": False, "cq:lastModified": "Tue Nov 10 2026", "jcr:title": "Home"}
EXISTING = {"777": {"classes": "text--hanging-asterisk", "label": "Hanging", "group": "item0",
                    "policy": "site/components/text/policy_2"}}


def project(tmp):
    root = Path(tmp)
    (root / "less").mkdir()
    (root / "less" / "x-blocks.less").write_text(".x-card { a: b; }\n.x-card--wide { a: b; }\n.x-mixin() { a: b; }\n.x-only-css { a: b; }\n")
    (root / "project.json").write_text(json.dumps({
        "aem": {"baseUrl": "http://aem", "policiesRoot": "/conf/site/settings/wcm/policies"},
        "damRoot": "/content/dam/site/new", "package": {"name": "p", "group": "g"},
        "pages": ["a.json"], "lessDir": "less", "classPrefix": "x-",
        "components": {"container": {"resourceType": "site/components/container", "policy": "site/components/container/policy_1"},
                       "text": {"resourceType": "site/components/text", "policy": "site/components/text/policy_2"}}}))
    (root / "a.json").write_text(json.dumps({"path": "/content/site/en/new", "mode": "create", "body": {"name": "root", "type": "container"}}))
    return Project.load(root)


class NewPageTests(unittest.TestCase):
    def test_inherits_typed_props_and_skips_timestamps(self):
        xml = page.render_new_page({"path": "/content/site/en/new", "pageProps": {"jcr:title": "New"}},
                                   PARENT, jcr.Node("root", {"jcr:primaryType": "nt:unstructured"}))
        self.assertIn('cq:template="/conf/site/settings/wcm/templates/content-page"', xml)
        self.assertIn('socialMedia="[facebook]"', xml)
        self.assertIn('hideInSearch="{Boolean}false"', xml)
        self.assertIn('jcr:title="New"', xml)
        self.assertNotIn("Tue Nov 10 2026", xml)
        self.assertIn('jcr:primaryType="cq:Page"', xml)

    def test_missing_template_is_an_error(self):
        with self.assertRaises(ConfigError):
            page.render_new_page({"path": "/x"}, {"sling:resourceType": "p"}, jcr.Node("root"))


class StyleRefTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = project(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_class_reference_resolves_on_the_components_policy(self):
        node = page.build_body({"name": "t", "type": "text", "styles": ["class:text--hanging-asterisk"]},
                               self.p, {}, existing=EXISTING)
        self.assertEqual(node.props["cq:styleIds"], ["777"])

    def test_class_reference_on_wrong_component_fails(self):
        with self.assertRaises(ConfigError):
            page.build_body({"name": "c", "type": "container", "styles": ["class:text--hanging-asterisk"]},
                            self.p, {}, existing=EXISTING)

    def test_style_coverage(self):
        spec = {"styles": {"container": [{"key": "a", "classes": "x-card"}, {"key": "b", "classes": "x-card x-card--wide"}]}}
        found = dict((m, lvl) for lvl, m in checks.check_style_coverage(spec, self.p.less_dir, "x-"))
        self.assertEqual(found.get("class .x-only-css is defined in LESS but not registered in any policy"), checks.ERROR)
        self.assertEqual(found.get("class .x-card--wide is only selectable inside a combined style"), checks.WARN)
        self.assertFalse(any("x-mixin" in m for m in found))


class CheckTests(unittest.TestCase):
    def test_missing_and_unused_assets(self):
        xml = 'fileReference="/content/dam/site/new/sub/a.svg" x="/content/dam/site/new/b.png"'
        found = checks.check_assets({"/p": xml}, ["sub/a.svg", "c.jpg"], "/content/dam/site/new")
        levels = sorted(level for level, _ in found)
        self.assertEqual(levels, [checks.ERROR, checks.WARN])

    def test_crop_rect_matches_verified_crop(self):
        t = [[0.1279287189245224, 0, 0.569008469581604], [0, 0.30846574902534485, 0.44404396414756775]]
        self.assertEqual(crop_rect(t, 4096, 3237), (2331, 1437, 524, 999))
        with self.assertRaises(ValueError):
            crop_rect([[0.5, 0.1, 0], [0, 0.5, 0]], 100, 100)


class FakeTarget:
    def __init__(self, existing_paths, policies):
        self.paths, self.policies_json = set(existing_paths), policies

    def policies(self, root):
        return self.policies_json

    def json(self, path, selector=None):
        if path in self.paths:
            return {}
        raise HttpError(f"404 {path}")


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = project(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_reports_missing_policy_id_clash_and_missing_reused_style(self):
        policies = {"site": {"components": {"container": {"policy_1": {"cq:styleGroups": {"item0": {"cq:styles": {
            "item0": {"cq:styleId": "100", "cq:styleClasses": "legacy", "cq:styleLabel": "L"}}}}}}}}}
        build = type("B", (), {"page_xml": {"/content/site/en/new": 'cq:styleIds="[100,555]" headerXf="/content/xf/header"'}})()
        spec = {"groupNode": "new2026", "styles": {"container": [{"key": "a", "classes": "x-card"}],
                                                   "text": [{"key": "b", "classes": "x-t"}]}}
        target = FakeTarget({"/content/site/en/jcr:content", "/content/dam/site"}, policies)
        messages = [m for _, m in preflight.run(target, self.p, build, {"a": "100", "b": "101"}, spec)]
        self.assertTrue(any("policy site/components/text/policy_2" in m for m in messages))
        self.assertTrue(any("style ID 100 is already used on the target by .legacy" in m for m in messages))
        self.assertTrue(any("existing style 555" in m for m in messages))
        self.assertTrue(any("/content/xf/header does not exist" in m for m in messages))


if __name__ == "__main__":
    unittest.main()
