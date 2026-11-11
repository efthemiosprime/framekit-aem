"""A small Figma snapshot (REST shapes per developers.figma.com) for design-system tests."""
import copy

ALIAS = lambda vid: {"type": "VARIABLE_ALIAS", "id": vid}  # noqa: E731
MARINE = {"r": 0, "g": 0x44 / 255, "b": 0x63 / 255, "a": 1}
WHITE = {"r": 1, "g": 1, "b": 1, "a": 1}
CORAL = {"r": 0xF8 / 255, "g": 0x8D / 255, "b": 0x78 / 255, "a": 1}

VARIABLES = {
    "variableCollections": {
        "C:prim": {"id": "C:prim", "name": "Primitives", "defaultModeId": "m:v",
                   "modes": [{"modeId": "m:v", "name": "Value"}]},
        "C:resp": {"id": "C:resp", "name": "Responsive", "defaultModeId": "m:d",
                   "modes": [{"modeId": "m:d", "name": "Desktop"}, {"modeId": "m:t", "name": "Tablet"},
                             {"modeId": "m:m", "name": "Mobile"}]},
        "C:theme": {"id": "C:theme", "name": "Theme", "defaultModeId": "m:l",
                    "modes": [{"modeId": "m:l", "name": "Light"}, {"modeId": "m:k", "name": "Dark"}]},
    },
    "variables": {
        "V:marine": {"id": "V:marine", "name": "color/marine/500", "variableCollectionId": "C:prim",
                     "resolvedType": "COLOR", "valuesByMode": {"m:v": MARINE}, "scopes": ["ALL_SCOPES"]},
        "V:white": {"id": "V:white", "name": "color/white", "variableCollectionId": "C:prim",
                    "resolvedType": "COLOR", "valuesByMode": {"m:v": WHITE}, "scopes": ["ALL_SCOPES"],
                    "codeSyntax": {"WEB": "var(--color-base-white)"}},
        "V:text": {"id": "V:text", "name": "color/text/primary", "variableCollectionId": "C:prim",
                   "resolvedType": "COLOR", "valuesByMode": {"m:v": ALIAS("V:marine")}},
        "V:section": {"id": "V:section", "name": "space/section", "variableCollectionId": "C:resp",
                      "resolvedType": "FLOAT", "valuesByMode": {"m:d": 96, "m:t": 64, "m:m": 40}},
        "V:h1": {"id": "V:h1", "name": "font/size/h1", "variableCollectionId": "C:resp",
                 "resolvedType": "FLOAT", "valuesByMode": {"m:d": 56, "m:t": 56, "m:m": 32}, "scopes": ["FONT_SIZE"]},
        "V:bold": {"id": "V:bold", "name": "font/weight/bold", "variableCollectionId": "C:prim",
                   "resolvedType": "FLOAT", "valuesByMode": {"m:v": 700}, "scopes": ["FONT_WEIGHT"]},
        "V:family": {"id": "V:family", "name": "font/family/body", "variableCollectionId": "C:prim",
                     "resolvedType": "STRING", "valuesByMode": {"m:v": "Museo Sans"}},
        "V:flag": {"id": "V:flag", "name": "feature/flag", "variableCollectionId": "C:prim",
                   "resolvedType": "BOOLEAN", "valuesByMode": {"m:v": True}},
        "V:surface": {"id": "V:surface", "name": "color/surface", "variableCollectionId": "C:theme",
                      "resolvedType": "COLOR", "valuesByMode": {"m:l": ALIAS("V:white"), "m:k": ALIAS("V:marine")}},
    },
}

STYLES = {
    "S:h1": {"key": "k1", "name": "Heading/H1", "styleType": "TEXT"},
    "S:body": {"key": "k2", "name": "Body/Regular", "styleType": "TEXT"},
    "S:coral": {"key": "k3", "name": "Brand/Coral", "styleType": "FILL"},
    "S:card": {"key": "k4", "name": "Elevation/Card", "styleType": "EFFECT"},
}

H1 = {"fontFamily": "Museo Sans", "fontPostScriptName": "MuseoSans-700", "fontWeight": 700, "fontSize": 56,
      "lineHeightPx": 64, "lineHeightUnit": "PIXELS", "letterSpacing": -0.5,
      "boundVariables": {"fontSize": ALIAS("V:h1")}}
BODY = {"fontFamily": "Museo Sans", "fontPostScriptName": "MuseoSans-500", "fontWeight": 500, "fontSize": 18,
        "lineHeightPercentFontSize": 133.33, "lineHeightUnit": "FONT_SIZE_%", "letterSpacing": 0}
SHADOW = [{"type": "DROP_SHADOW", "visible": True, "color": {"r": 0, "g": 0, "b": 0, "a": 0.25},
           "offset": {"x": 0, "y": 4}, "radius": 12, "spread": 0}]


def button(node_id, name, fill_style=None):
    node = {"id": node_id, "name": name, "type": "COMPONENT", "layoutMode": "HORIZONTAL",
            "primaryAxisAlignItems": "CENTER", "counterAxisAlignItems": "CENTER",
            "itemSpacing": 8, "paddingTop": 12, "paddingBottom": 12, "paddingLeft": 32, "paddingRight": 32,
            "cornerRadius": 100, "fills": [{"type": "SOLID", "color": WHITE}],
            "strokes": [{"type": "SOLID", "color": CORAL}], "strokeWeight": 2,
            "children": [{"id": node_id + "t", "name": "Label", "type": "TEXT", "style": BODY, "styles": {"text": "S:body"},
                          "fills": [{"type": "SOLID", "color": MARINE, "boundVariables": {"color": ALIAS("V:text")}}]}]}
    if fill_style:
        node["styles"] = {"fill": fill_style}
        node["fills"] = [{"type": "SOLID", "color": CORAL}]
        node["strokes"] = []
    return node


def frame(node_id, width, grid, children):
    return {"document": {"id": node_id, "name": f"Home {width}", "type": "FRAME", "layoutGrids": [grid],
                         "fills": [{"type": "SOLID", "color": WHITE}], "children": children},
            "components": {"C:btn1": {"name": "Type=Primary", "componentSetId": "CS:btn"}},
            "componentSets": {"CS:btn": {"name": "Button"}},
            "styles": STYLES}


DESKTOP = frame("1:1", 1440, {"pattern": "COLUMNS", "count": 12, "gutterSize": 24, "offset": 96,
                              "alignment": "STRETCH", "visible": True}, [
    {"id": "1:10", "name": "Hero", "type": "FRAME", "layoutMode": "VERTICAL", "itemSpacing": 24,
     "paddingTop": 96, "paddingBottom": 96, "boundVariables": {"paddingTop": ALIAS("V:section"),
                                                               "paddingBottom": ALIAS("V:section")},
     "fills": [{"type": "SOLID", "color": MARINE, "boundVariables": {"color": ALIAS("V:marine")}}],
     "effects": SHADOW, "styles": {"effect": "S:card"},
     "children": [
         {"id": "1:11", "name": "Title", "type": "TEXT", "style": H1, "styles": {"text": "S:h1"},
          "fills": [{"type": "SOLID", "color": WHITE}]},
         {"id": "1:12", "name": "Note", "type": "TEXT", "fills": [{"type": "SOLID", "color": WHITE}],
          "style": {"fontFamily": "Museo Sans", "fontWeight": 500, "italic": True, "fontSize": 15,
                    "lineHeightUnit": "INTRINSIC_%"}},
         {"id": "1:13", "name": "Button", "type": "INSTANCE", "componentId": "C:btn1",
          "componentProperties": {"Type": {"type": "VARIANT", "value": "Primary"}},
          **{k: v for k, v in button("1:13", "x", "S:coral").items() if k not in ("id", "name", "type")}},
         {"id": "1:14", "name": "Hidden", "type": "TEXT", "visible": False,
          "style": {"fontFamily": "Comic Sans", "fontWeight": 400, "fontSize": 99}},
     ]},
])
TABLET = frame("1:2", 768, {"pattern": "COLUMNS", "count": 8, "sectionSize": 72, "gutterSize": 24,
                            "alignment": "CENTER", "visible": True}, [])
MOBILE = frame("1:3", 360, {"pattern": "COLUMNS", "count": 4, "gutterSize": 16, "offset": 20,
                            "alignment": "STRETCH", "visible": True}, [])
COMPONENTS = {"document": {"id": "9:1", "name": "Components", "type": "CANVAS", "children": [
    {"id": "9:2", "name": "Button", "type": "COMPONENT_SET", "children": [
        button("9:3", "Type=Primary", "S:coral"),
        button("9:4", "Type=Secondary"),
    ]}]}, "components": {}, "componentSets": {}, "styles": STYLES}


def snapshot(with_variables=True):
    """A fresh deep copy, so a test may mutate it."""
    return copy.deepcopy({
        "fileKey": "FILE",
        "variables": VARIABLES if with_variables else None,
        "variablesError": None if with_variables else "HTTP 403: Limited by Figma plan",
        "frames": [
            {"id": "1:1", "width": 1440, "breakpoint": "desktop", "payload": DESKTOP},
            {"id": "1:2", "width": 768, "breakpoint": "tablet", "payload": TABLET},
            {"id": "1:3", "width": 360, "breakpoint": "mobile", "payload": MOBILE},
            {"id": "9:1", "width": None, "breakpoint": None, "payload": COMPONENTS},
        ],
    })
