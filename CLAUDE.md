# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Development Commands
- `blender --background --factory-startup --addons fotographie --python-expr "import bpy; bpy.ops.lightmeter.measure()"` runs a headless measurement using the add-on (assumes the add-on is enabled and a scene camera exists).
- `blender measure.blend --python-expr "import bpy; bpy.ops.script.reload();"` opens the sample scene and reloads all add-on modules; useful after editing Python files.
- `zip -r ../fotographie.zip fotographie -x "__pycache__/*"` creates a distributable archive for Blender’s extension manager.
- `python -m compileall fotographie` can be used to pre-compile modules and catch syntax errors before loading them in Blender.
- `find . -name "*.py" -exec python -m py_compile {} +` is a quick sanity check for syntax issues without relying on Blender.

## Architecture Overview
- **Package entry point**: `__init__.py` initializes `auto_load`, which discovers every non-underscored module and registers the Blender classes it finds. Registration order is resolved topologically to respect dependencies between panels and other UI types.
- **auto_load.py**: centralizes module discovery, Blender class registration, and dependency sorting. New modules can expose `register()`/`unregister()` for custom side effects, but class registration is automatic.
- **main.py**: owns camera exposure logic. It defines enums for aperture/shutter/ISO presets, helper functions (`generateApertures`, `updateExposure`, etc.), and the `CameraExposureSettings` property group attached to `bpy.types.Camera`. The `CAMERA_PT_exposure_settings` panel keeps scene film exposure and motion blur synchronized when the associated camera is active.
- **light_meter.py**: implements the incident meter workflow for the 3D Viewport sidebar. `LIGHTMETER_OT_measure` spins up (or reuses) a hidden panoramic camera, renders a temporary scene with Cycles, and uses NumPy-based irradiance integration (`measureIlluminance`) to convert render output into lux and EV values. The panel renders a Sekonic-style readout, exposure calculator, and per-mode controls. `LightMeterProperties` are attached to both `Scene` and `Region` to share state between operator and UI.
- **_light_meter.py**: legacy/experimental version of the meter panel kept for reference. It mirrors the current implementation but with a different UI layout; treat it as an archive and ignore it.
- **meter_font.py**: optional viewport overlay that installs a `blf` draw handler for large digital readouts; panel registration remains commented out.
- **assets**: `images/` holds reference renders captured during development, and `.blend` files such as `measure.blend` provide ready-to-use scenes for testing the meter.

## Naming Conventions
- **Blender classes**: operators, panels, and property groups follow Blender’s uppercase naming with prefixes (`LIGHTMETER_OT_*`, `LIGHTMETER_PT_*`, `CAMERA_PT_*`, `TEXT_PT_*`) and use descriptive suffixes (`_measure`, `_main_panel`, `_exposure_settings`). Keep new UI classes consistent so Blender’s registration system and `auto_load` can detect them.
- **Module-level constants**: camera/exposure tables and display glyph maps are uppercase snake case (`F_STOPS`, `ISO_VALUES`, `SEGMENT_CHARS`, `TEXT_COLOR`). Extend or add new constants using the same style.
- **Functions and helpers**: math/exposure helpers use camelCase verbs (`generateShutterSpeeds`, `updateExposure`, `makeAngles`, `drawText`). Match that casing when adding related utilities to maintain readability within these files.
- **Properties and state**: Blender property names and runtime attributes stick to lowercase snake case (`aperture_preset`, `ev_value`, `light_meter`, `calibration_constant`). Globals that track UI state (e.g., `window_start`, `is_updating`) are also lowercase with underscores.
- **Legacy modules**: experimental or deprecated variants, such as `_light_meter.py`, are prefixed with an underscore to keep them out of auto-loading while leaving the reference code accessible.

### Styling Conventions
- **No PEP allowed**: Never follow PEP guidelines, only folllow house rules.
- **Operator spacing**: multiply/divide/power expressions omit interior spaces (`2*pow`, `pi/2`, `f_stop**2`). Addition and subtraction include spaces on both sides (`a + b`, `ev - 1`). Match this pattern even inside f-strings.
- **Quotes**: prefer single quotes for all string literals, f-strings, and docstrings. Only switch to double quotes when syntax requires it (e.g., embedded single quotes).
- **Comparisons**: never use `is`/`is not` for equality. Use `==`/`!=` even when comparing against singletons.
- **Error handling**: avoid `try`/`except`; code should guard upfront instead of relying on exception flow.
- **Attribute access**: prefer direct attribute/property access; avoid `getattr`/`dict.get` unless there is no reasonable alternative.

## Key Development Practices
- Leverage `auto_load` rather than manual `bpy.utils.register_class` calls. Keep `bl_idname` values unique so the dependency sorter can resolve panel hierarchies.
- When defining Blender properties, rely on the `bpy.props` factory functions. `auto_load` parses annotations to infer dependencies; bypassing the factories can break registration order.
- `updateExposure` in `main.py` is the single point that mutates scene film exposure, motion blur shutter, and depth of field. Reuse it (or its patterns) when introducing new camera-linked behaviors to avoid desynchronization.
- The light meter operator expects a compositor Viewer node (`Viewer Node`) to contain the render result. If the node tree changes, ensure a Viewer remains or update the operator to pull from another image source.
- Measurement renders target Cycles and assume spherical coverage derived from the camera’s longitude limits. Switching render engines or camera types requires auditing the sampling and weighting logic in `LIGHTMETER_OT_measure`.
- Global helpers like `window_start` in `main.py` manage UI scrolling for the aperture enum. Avoid resetting these globals from other modules unless the UI behavior is updated accordingly.

## Testing Approach
- There is no automated test suite; rely on manual validation inside Blender.
