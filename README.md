# Parametric Stairs from Planes

A Blender add-on for developing stairs and railings from reference meshes or parametric inputs. Includes architectural coordination and quantity-estimating tools.

**Version:** 7.4.0 · **Target:** Blender 5.2.2 · **Status:** development preview

> The current package has not been tested in Blender 5.2.2. Review it on a copy of a project before using its outputs. This is not a finished commercial release or a substitute for building-code, structural, or professional review.

## What's included

- Plane-driven and parametric stair generation, including straight, L, U, multi-flight, curved, helical and spiral layouts as implemented in the add-on.
- Stair structure, tread, riser, landing, nosing, finish, material and lighting controls.
- A library of 33 railing style definitions with generated preview icons, plus standalone edge-driven railings.
- Per-edge railing controls, optional wall detection, and editable reference-edge markings for plane-driven stairs.
- Finished-floor reference offsets, dimensional targets, stairwell fit comparison and a slab-opening tool.
- Sampled headroom, surface-intersection review, schematic SVG plan and cut-section exports, and estimated quantities with CSV export.
- Draft viewport display and project presets.

These features describe the code supplied; actual geometry, performance and compatibility require Blender testing.

## Installation

1. Download the release ZIP without extracting it.
2. In Blender, open **Edit → Preferences → Add-ons**, then open the top-right menu and choose **Install from Disk**.
3. Select the ZIP and enable **Parametric Stairs from Planes**. If an older copy is installed, disable or remove it first to avoid registration conflicts.
4. In the 3D Viewport press **N**, then open the **Stairs** tab.

This package is a legacy add-on ZIP, not a Blender Extensions Platform package. See [Blender's add-on installation instructions](https://docs.blender.org/manual/en/5.2/editors/preferences/addons.html).

Read [USER_GUIDE.md](oliver_stairs/USER_GUIDE.md) for workflows, limitations and troubleshooting.

## Development

The installable source is [oliver_stairs/__init__.py](oliver_stairs/__init__.py). It is intentionally kept in one file to preserve the existing implementation. Run `python -m unittest discover -s tests` for the dependency-free logic checks. These tests do not execute Blender or validate the user interface or geometry engine.

## Release readiness

Before selling or distributing this add-on, test installation and all critical modelling workflows in the target Blender version, validate exported geometry and quantities, select appropriate licensing, and review third-party attribution. No licence or commercial support terms have been selected in this package.
