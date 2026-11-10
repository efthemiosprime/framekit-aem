"""Offline tests: python3 -m unittest discover -s tests"""
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.dom import minidom

from figma2aem import jcr, lessgen, mapping, page, styles, verify
from figma2aem.config import ConfigError, Project
from figma2aem.figma_client import FigmaClient

PAGE_PATH = "/content/site/us/en"
BASE_PAGE_XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<jcr:root xmlns:jcr="http://www.jcp.org/jcr/1.0" xmlns:cq="http://www.day.com/jcr/cq/1.0" xmlns:sling="http://sling.apache.org/jcr/sling/1.0" xmlns:nt="http://www.jcp.org/jcr/nt/1.0"
    jcr:primaryType="cq:Page">
    <jcr:content
        cq:lastModified="{{Date}}2020-01-01T00:00:00.000Z"
        cq:template="/conf/site/settings/wcm/templates/content-page"
        jcr:primaryType="cq:PageContent"
        jcr:title="Old home"
        sling:resourceType="site/components/page">
        <root jcr:primaryType="nt:unstructured" sling:resourceType="site/components/container"/>
    </jcr:content>
</jcr:root>
"""


def make_project(tmp):
    root = Path(tmp)
    base = root / "base.zip"
    with zipfile.ZipFile(base, "w") as zf:
        zf.writestr(f"jcr_root{PAGE_PATH}/.content.xml", BASE_PAGE_XML)
    (root / "assets").mkdir()
    png = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + (16).to_bytes(4, "big") + (9).to_bytes(4, "big") + b"\x08\x02\x00\x00\x00"
    (root / "assets" / "hero.png").write_bytes(png)
    (root / "project.json").write_text(json.dumps({
        "aem": {"baseUrl": "http://aem", "policiesRoot": "/conf/site/settings/wcm/policies"},
        "damRoot": "/content/dam/site/new",
        "package": {"name": "site-home", "group": "site"},
        "components": {
            "container": {"resourceType": "site/components/container", "policy": "site/components/container/policy_1"},
            "text": {"resourceType": "site/components/text", "policy": "site/components/text/policy_2",
                     "defaults": {"textIsRich": "true"}},
            "teaser": {"resourceType": "site/components/teaser"},
        },
    }))
    (root / "styles.json").write_text(json.dumps({
        "groupLabel": "New", "groupNode": "new2026", "idBase": 100,
        "styles": {"container": [{"key": "section", "classes": "x-section", "label": "Section"}],
                   "text": [{"key": "lead", "classes": "x-lead", "label": "Lead"}]},
    }))
    (root / "page.json").write_text(json.dumps({
        "path": PAGE_PATH, "basePackage": "base.zip",
        "assets": [{"file": "hero.png", "title": "Hero"}],
        "verify": {"url": "http://aem/en.html", "viewports": [{"width": 1440, "figmaFrame": "1:1"}]},
        "body": {"name": "root", "type": "container", "children": [
            {"name": "intro", "type": "container", "styles": ["section"], "props": {"backgroundImageReference": "dam:hero.png"},
             "verify": {"figma": "Intro", "selector": ".x-section"},
             "children": [{"name": "lead", "type": "text", "styles": ["lead"], "props": {"text": "<p>Hi & welcome</p>"}}]},
            {"name": "card", "type": "teaser", "actions": [{"link": "/content/site/us/en/a", "text": "Go"}]},
        ]},
    }))
    return Project.load(root)


class JcrTests(unittest.TestCase):
    def test_values(self):
        self.assertEqual(jcr.format_value(True), "{Boolean}true")
        self.assertEqual(jcr.format_value(jcr.Long(5)), "{Long}5")
        self.assertEqual(jcr.format_value(["a,b", "c"]), "[a\\,b,c]")
        self.assertEqual(jcr.format_value("[not a list"), "\\[not a list")
        with self.assertRaises(TypeError):
            jcr.format_value(5)

    def test_escaping_and_vault_path(self):
        node = jcr.Node("n", {"text": '<p class="x">a&b\n</p>'})
        self.assertIn('text="&lt;p class=&quot;x&quot;&gt;a&amp;b&#xa;&lt;/p&gt;"', node.to_xml())
        self.assertEqual(jcr.vault_path("/a/cq:styleGroups/g"), "/a/_cq_styleGroups/g")


class StyleIdTests(unittest.TestCase):
    spec = {"styles": {"c": [{"key": "a"}, {"key": "b"}]}, "idBase": 10}

    def test_new_ids_skip_taken(self):
        self.assertEqual(styles.assign_ids(self.spec, {}, {"10", "11"}), {"a": "12", "b": "13"})

    def test_lock_is_stable_even_when_ids_exist_in_aem(self):
        lock = {"a": "10", "b": "11"}
        self.assertEqual(styles.assign_ids(self.spec, lock, {"10", "11"}, own_ids={"10", "11"}), lock)

    def test_lock_clash_with_foreign_style_fails(self):
        with self.assertRaises(ConfigError):
            styles.assign_ids(self.spec, {"a": "10"}, {"10"}, own_ids=set())


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.project = make_project(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_page_render_keeps_page_props_and_builds_body(self):
        ids = {"section": "100", "lead": "101"}
        body = page.build_body(self.project.page()["body"], self.project, ids)
        base = page.page_xml_from_package(self.project.path("base.zip"), PAGE_PATH)
        xml = page.render_page(base, body)
        self.assertIn('cq:template="/conf/site/settings/wcm/templates/content-page"', xml)
        self.assertNotIn("2020-01-01", xml)
        self.assertIn('cq:styleIds="[100]"', xml)
        self.assertIn('backgroundImageReference="/content/dam/site/new/hero.png"', xml)
        self.assertIn('textIsRich="true"', xml)
        self.assertIn("&lt;p&gt;Hi &amp; welcome&lt;/p&gt;", xml)
        self.assertIn('link="/content/site/us/en/a"', xml)
        self.assertEqual(minidom.parseString(xml.encode()).documentElement.tagName, "jcr:root")

    def test_unknown_style_key_is_rejected(self):
        spec = {"name": "x", "type": "text", "styles": ["missing"]}
        with self.assertRaises(ConfigError):
            page.build_body(spec, self.project, {})

    def test_missing_template_refuses_to_build(self):
        with self.assertRaises(ConfigError):
            page.render_page(BASE_PAGE_XML.replace("cq:template", "cq:other"), jcr.Node("root"))

    def test_style_group_entries_and_filters(self):
        spec = self.project.styles()
        entries, filters = styles.package_entries(spec, {"section": "100", "lead": "101"}, self.project)
        self.assertIn("/conf/site/settings/wcm/policies/site/components/container/policy_1/cq:styleGroups/new2026", filters)
        name = "jcr_root/conf/site/settings/wcm/policies/site/components/container/policy_1/_cq_styleGroups/new2026/.content.xml"
        self.assertIn(b'cq:styleId="100"', entries[name])

    def test_scaffold_never_overwrites(self):
        name, text = lessgen.scaffold(self.project.styles(), self.project.page(), "section")
        self.assertEqual(name, "ds-x-section.less")
        self.assertIn(".x-section {", text)
        path, created = lessgen.write_scaffold(self.tmp, name, text)
        self.assertTrue(created)
        path.write_text("custom")
        _, created_again = lessgen.write_scaffold(self.tmp, name, text)
        self.assertFalse(created_again)
        self.assertEqual(path.read_text(), "custom")


class FigmaTests(unittest.TestCase):
    payload = {
        "document": {"id": "1:1", "name": "Page", "type": "FRAME", "absoluteBoundingBox": {"x": 100, "y": 50, "width": 1440, "height": 900},
                     "children": [
                         {"id": "2:1", "name": "Intro", "type": "INSTANCE", "componentId": "c1",
                          "absoluteBoundingBox": {"x": 100, "y": 120, "width": 1440, "height": 600},
                          "componentProperties": {"Size": {"type": "VARIANT", "value": "L"}},
                          "children": [{"id": "I2:1;3:1", "name": "Nested", "type": "INSTANCE", "componentId": "c2"}]},
                         {"id": "2:2", "name": "Button", "type": "INSTANCE", "componentId": "c2", "visible": False},
                     ]},
        "components": {"c1": {"name": "Size=L", "componentSetId": "s1"}, "c2": {"name": "Button"}},
        "componentSets": {"s1": {"name": "Hero"}},
    }

    def test_inventory_counts_outermost_instances(self):
        inv = mapping.figma_inventory(self.payload, {"Hero": "hero"})
        self.assertEqual([g["component"] for g in inv], ["Hero", "Button"])
        self.assertEqual(inv[0]["aemType"], "hero")
        self.assertEqual(list(inv[0]["variants"]), ["Size=L"])
        self.assertEqual(inv[1]["variants"]["(no variants)"]["hidden"], 1)

    def test_verify_spec_uses_frame_relative_boxes(self):
        page_spec = {"verify": {"url": "u", "viewports": [{"width": 1440, "figmaFrame": "1-1"}]},
                     "body": {"name": "root", "type": "container", "verify": {"figma": ["Missing", "Intro"], "selector": ".x"}}}
        spec = verify.build_spec(page_spec, {"1:1": self.payload})
        check = spec["viewports"][0]["checks"][0]
        self.assertEqual(check["figma"], "Intro")
        self.assertEqual(check["expected"], [0, 70, 1440, 600])

    def test_client_builds_urls_and_reports_missing(self):
        calls = []

        def fake(url, headers):
            calls.append((url, headers))
            return {"nodes": {"1:1": None}}

        client = FigmaClient("tok", "KEY", fetch_json=fake)
        with self.assertRaises(Exception):
            client.nodes(["1-1"])
        self.assertIn("files/KEY/nodes?ids=1%3A1", calls[0][0])
        self.assertEqual(calls[0][1], {"X-Figma-Token": "tok"})


class AemInventoryTests(unittest.TestCase):
    def test_style_ids_resolve_to_classes(self):
        policies = {"site": {"components": {"text": {"policy_2": {"cq:styleGroups": {"item0": {"cq:styles": {
            "item0": {"cq:styleId": "7", "cq:styleClasses": "x-lead", "cq:styleLabel": "Lead"}}}}}}}}}
        index = mapping.style_index(policies)
        rows = mapping.aem_tree({"root": {"sling:resourceType": "site/components/container",
                                          "t": {"sling:resourceType": "site/components/text", "cq:styleIds": ["7", ""]}}}, index)
        self.assertEqual(rows[1]["classes"], "x-lead")
        self.assertEqual(index["7"]["policy"], "site/components/text/policy_2")


if __name__ == "__main__":
    unittest.main()
