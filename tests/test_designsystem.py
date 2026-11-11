"""Offline tests for the Figma → design-system LESS layer: python3 -m unittest discover -s tests"""
import copy
import unittest

from figma2aem import designsystem as ds
from figma2aem.net import HttpError

import figma_fixture as F

RES = "/etc.clientlibs/acme/clientlibs/clientlib-acme/resources/"


def build(snapshot=None, **kw):
    kw.setdefault("resources_url", RES)
    files, report, missing = ds.build(F.snapshot() if snapshot is None else snapshot, "ds-", **kw)
    return files, report, missing


def block(text, header):
    """Lines of the block that starts at `header` (exact line) up to its closing brace."""
    lines = text.splitlines()
    start = lines.index(header)
    end = next(i for i in range(start, len(lines)) if lines[i] == "}")
    return lines[start:end + 1]


class HelpersTest(unittest.TestCase):
    def test_color(self):
        self.assertEqual(ds.color(F.MARINE), "#004463")
        self.assertEqual(ds.color({"r": 0, "g": 0, "b": 0, "a": 0.5}), "rgba(0, 0, 0, 0.5)")
        self.assertEqual(ds.color(F.WHITE, opacity=0.25), "rgba(255, 255, 255, 0.25)")

    def test_slug_and_numbers(self):
        self.assertEqual(ds.slug("Heading/H1 Large"), "heading-h1-large")
        self.assertEqual(ds.slug("fontSize"), "font-size")
        self.assertEqual(ds.px(0), "0")
        self.assertEqual(ds.px(12.5), "12.5px")

    def test_alias_ids_accepts_single_or_list(self):
        self.assertEqual(ds.alias_ids(F.ALIAS("V:1")), ["V:1"])
        self.assertEqual(ds.alias_ids([F.ALIAS("V:1"), F.ALIAS("V:2")]), ["V:1", "V:2"])
        self.assertEqual(ds.alias_ids(None), [])

    def test_node_style_id_any_case(self):
        self.assertEqual(ds.node_style_id({"styles": {"FILL": "S:1"}}, "fill"), "S:1")
        self.assertEqual(ds.node_style_id({"styles": {"fills": "S:2"}}, "fill"), "S:2")

    def test_breakpoints(self):
        self.assertEqual([ds.breakpoint_for_width(w, ds.DEFAULT_BREAKPOINTS) for w in (1440, 1024, 1023, 768, 767, 360)],
                         ["desktop", "desktop", "tablet", "tablet", "mobile", "mobile"])
        self.assertEqual(ds.mode_breakpoint("Mobile (360)", ds.DEFAULT_BREAKPOINTS), "mobile")
        self.assertIsNone(ds.mode_breakpoint("Dark", ds.DEFAULT_BREAKPOINTS))

    def test_variant_name_parsing(self):
        self.assertEqual(dict(ds.parse_variant_name("Type=Primary, Size=Large")), {"Type": "Primary", "Size": "Large"})
        self.assertEqual(ds.variant_names([(("Type", "A"),), (("Type", "B"),)]), ["a", "b"])
        self.assertEqual(ds.variant_names([(("Type", "A"), ("On", "x")), (("Type", "A"), ("Off", "x"))]),
                         ["type-a--on-x", "type-a--off-x"])


class TokensTest(unittest.TestCase):
    def test_root_values_aliases_and_code_syntax(self):
        root = block(build()[0]["tokens.less"], ":root {")
        self.assertIn("    --color-base-white: #ffffff;", root)          # codeSyntax.WEB wins
        self.assertIn("    --color-text-primary: var(--color-marine-500);", root)  # alias
        self.assertIn("    --font-weight-bold: 700;", root)               # FONT_WEIGHT scope → unitless
        self.assertIn("    --space-section: 96px;", root)                 # default mode = Desktop
        self.assertIn('    --font-family-body: "Museo Sans";', root)
        self.assertIn("    --color-brand-coral: #f88d78;", root)          # fill style
        self.assertIn("    --shadow-elevation-card: 0 4px 12px 0 rgba(0, 0, 0, 0.25);", root)
        self.assertFalse(any("flag" in line for line in root))           # booleans skipped

    def test_responsive_modes_compare_with_next_wider(self):
        snap = F.snapshot()
        snap["variables"]["variables"]["V:h1"]["valuesByMode"] = {"m:d": 56, "m:t": 44, "m:m": 56}
        text = build(snap)[0]["tokens.less"]
        tablet = text[text.index("max-width: 1023px"):text.index("max-width: 767px")]
        mobile = text[text.index("max-width: 767px"):]
        self.assertIn("--font-size-h1: 44px;", tablet)
        self.assertIn("--font-size-h1: 56px;", mobile)  # undo tablet, though equal to desktop
        self.assertNotIn("@ds-mq", text)  # literal queries: LESS 1.7.5 cannot interpolate in @media

    def test_unchanged_modes_are_not_repeated(self):
        text = build()[0]["tokens.less"]
        tablet = text[text.index("max-width: 1023px"):text.index("max-width: 767px")]
        self.assertNotIn("--font-size-h1", tablet)  # 56 on Desktop and Tablet

    def test_non_responsive_modes_use_data_attribute(self):
        self.assertIn('[data-theme="dark"] {\n    --color-surface: var(--color-marine-500);\n}',
                      build()[0]["tokens.less"])

    def test_scoped_tokens_redeclare_aliases(self):
        text = build(scope=".ds-section")[0]["tokens.less"]
        mobile = text[text.index("max-width: 767px"):]
        self.assertIn(".ds-section", text)
        self.assertIn("--color-text-primary: var(--color-marine-500);", mobile)

    def test_without_variables_falls_back_to_styles(self):
        files, report, _ = build(F.snapshot(with_variables=False))
        self.assertIn("No Figma variables", files["tokens.less"])
        self.assertIn("--color-brand-coral: #f88d78;", files["tokens.less"])
        self.assertIn("Limited by Figma plan", report)
        # bound font size cannot be resolved without variables → raw value
        self.assertIn("--type-heading-h1-font-size: 56px;", files["typography.less"])


class FoundationsTest(unittest.TestCase):
    def test_grid_per_breakpoint_resets_every_key(self):
        text = build()[0]["grid.less"]
        self.assertIn('@ds-mq-mobile: ~"screen and (max-width: 767px)";', text)
        self.assertIn("    --grid-columns: 12;", block(text, ":root {"))
        tablet = text[text.index("max-width: 1023px) {"):text.index("max-width: 767px) {")]
        self.assertIn("--grid-max-width: 744px;", tablet)  # CENTER: 8 × 72 + 7 × 24
        mobile = text[text.index("max-width: 767px) {"):]
        self.assertIn("--grid-max-width: none;", mobile)    # otherwise tablet's value leaks

    def test_spacing_defines_every_raw_value_handed_out(self):
        files = build()[0]
        spacing = files["spacing.less"]
        for value in ("8", "12", "24", "32"):
            self.assertIn(f"--space-{value}: {value}px;", spacing)
        self.assertIn("--radius-100: 100px;", spacing)
        self.assertNotIn("--space-96", spacing)  # bound to space/section

    def test_fonts(self):
        files, _, missing = build()
        self.assertIn("MuseoSans-700.woff2", files["fonts.less"])
        self.assertIn("font-style: italic;", files["fonts.less"])   # unstyled italic text counts
        self.assertNotIn("Comic Sans", files["fonts.less"])         # hidden layer ignored
        self.assertEqual(sorted(missing), ["MuseoSans-500.woff2", "MuseoSans-500Italic.woff2", "MuseoSans-700.woff2"])
        files, _, missing = build(font_files=["MuseoSans-700.woff2", "MuseoSans-700.woff"])
        self.assertIn("MuseoSans-700.woff2') format('woff2'), url('" + RES + "fonts/MuseoSans-700.woff') format('woff')",
                      files["fonts.less"])
        self.assertNotIn("MuseoSans-700.woff2", missing)

    def test_fonts_without_resources_url(self):
        text = build(resources_url="")[0]["fonts.less"]
        self.assertNotIn("@font-face {", text)
        self.assertIn("clientlib.appsPath", text)

    def test_typography(self):
        text = build()[0]["typography.less"]
        self.assertIn("--type-heading-h1-font-size: var(--font-size-h1);", text)  # bound variable
        self.assertIn("--type-body-regular-line-height: 1.333;", text)            # FONT_SIZE_%
        self.assertIn(".ds-type--heading-h1() {", text)
        self.assertTrue(text.startswith(ds.GENERATED))


class VariantsTest(unittest.TestCase):
    def test_definitions_win_and_styles_resolve(self):
        text = build(component_map={"Button": "button"})[0]["variants.less"]
        self.assertIn("// ---- Button  → AEM button", text)
        self.assertIn("(Figma component 9:3)", text)  # not the instance 1:13
        primary = block(text, ".ds-variant--button--primary() {")
        self.assertIn("    background: var(--color-brand-coral);", primary)
        self.assertIn("    padding: var(--space-12) var(--space-32) var(--space-12) var(--space-32);", primary)
        secondary = block(text, ".ds-variant--button--secondary() {")
        self.assertIn("    border: 2px solid #f88d78;", secondary)
        label = block(text, ".ds-variant--button--primary--text() {")
        self.assertIn("    .ds-type--body-regular();", label)
        self.assertIn("    color: var(--color-text-primary);", label)

    def test_report_counts_each_node_once(self):
        report = build()[1]
        self.assertIn("Spacing (16 uses, bound 2)", report)
        self.assertIn("Font sizes without a text style (1 uses): 15px×1", report)

    def test_empty_snapshot_still_renders(self):
        files, report, missing = ds.build(None, "ds-")
        self.assertEqual(set(files), {"tokens.less", "spacing.less", "grid.less", "fonts.less",
                                      "typography.less", "variants.less", "index.less"})
        self.assertEqual(missing, [])


class SnapshotTest(unittest.TestCase):
    class FakeClient:
        file_key = "FILE"

        def __init__(self, variables_error=None):
            self.variables_error = variables_error
            self.requested = None

        def nodes(self, ids):
            self.requested = ids
            return {i: {"document": {"id": i}} for i in ids}

        def local_variables(self):
            if self.variables_error:
                raise HttpError(self.variables_error)
            return copy.deepcopy(F.VARIABLES)

    def test_frames_dedupe_and_breakpoints(self):
        client = self.FakeClient()
        snap = ds.figma_snapshot(client, [("1:1", 1440), ("1:3", 360), ("1:1", 1440)], ["9:1"])
        self.assertEqual(client.requested, ["1:1", "1:3", "9:1"])
        self.assertEqual([(f["id"], f["breakpoint"]) for f in snap["frames"]],
                         [("1:1", "desktop"), ("1:3", "mobile"), ("9:1", None)])
        self.assertIn("variables", snap["variables"])

    def test_variables_403_is_recorded_not_fatal(self):
        snap = ds.figma_snapshot(self.FakeClient("HTTP 403: Limited by Figma plan"), [("1:1", 1440)],
                                 http_error=HttpError)
        self.assertIsNone(snap["variables"])
        self.assertIn("403", snap["variablesError"])

    def test_no_frames_is_an_error(self):
        with self.assertRaises(ValueError):
            ds.figma_snapshot(self.FakeClient(), [])


if __name__ == "__main__":
    unittest.main()
