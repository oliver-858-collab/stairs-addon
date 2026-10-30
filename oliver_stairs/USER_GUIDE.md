# User guide — Parametric Stairs from Planes 7.4.0

## Before you begin

This is a development preview, not a certified construction design tool. Keep a backup of your `.blend` file. Blender 5.2.2 is the intended target but has not been tested by the package author in this environment. The add-on's declared minimum Blender version is 3.6; that declaration is not evidence of compatibility testing.

## Install and find the controls

1. Open **Edit → Preferences → Add-ons** and use the top-right menu → **Install from Disk** to select the ZIP. Enable the add-on.
2. Disable any older copy first. Restart Blender if you encounter duplicate registration or stale controls.
3. In the 3D Viewport press **N** and open **Stairs**.

The generated railing style preview icons are created when the add-on loads and cached in Blender's user configuration directory, with a temporary-directory fallback.

## Create a stair

### From a reference plane

1. Select the mesh that describes the stair. Sloping faces represent flights; flat faces represent landings.
2. Use the plane-driven engine and choose dimensions, stair type and finishes.
3. Select **Generate Stairs**. Keep the control mesh: it drives later changes.
4. Change settings and use **Update Now**, or use live updates where appropriate.

### Parametric layout

1. Choose **Add Parametric Stair** in the Stairs panel.
2. In the parametric engine controls choose a layout and set floor height, width, riser target, going and landings.
3. Optionally reference lower and upper floor objects. Their reference elevation is based on the centre of their bounding box; use the finished-floor offsets to reach the intended finished level.
4. Check the measured output in **Stair Stats**. Actual riser heights may differ from the target to meet the total rise.

## Stairwell fitting and openings

In **Stairwell Fit**, set the void size or select a void object, define the start edge and minimum width, then use **Compare Fit Options**. Review the listed candidates and choose a layout before using **Fit Stair to Void**. The solver uses built-in assumptions; it does not establish code compliance. The fit operation changes stair settings and placement.

The slab-opening tool can use a live Boolean. **Make Permanent** applies a change to the slab; use it only after reviewing the opening and backing up the model.

## Railings

### Control individual stair edges

For plane-driven stairs, select the reference mesh, enter Edit Mode, select its edge, then use **Railings → Remove Railing**. Use **Restore Railing** to restore the previous edge setting. **Force Railing on Selected** assigns a railing even where automatic wall detection would exclude that edge. Edge controls do not apply to virtual parametric layouts.

Enable **Detect Walls** and select a wall collection for explicit control. Without a collection, the current implementation looks for mesh objects with `wall` in their names. Tune detection distance and probe height; wall detection is approximate. Use **Update Now** after moving a wall.

### Standalone railings

1. Select a plane or mesh and enter Edit Mode.
2. Select the edges to receive railings.
3. Open **Standalone Railings**, pick a visual style and dimensions, and click **Generate / Update Railings**.
4. In Object Mode, update the railing from its saved edge selection. Use **Remove Standalone Railings** to remove the generated output.

Connected, non-branching paths and loops are supported by the code. Branching selections are rejected; use separate source meshes or non-branching selections. Inspect corners and all connections in Blender before use.

## Architectural coordination

- **Stair Stats:** review measured rise, going, flight width, run and user-defined target warnings. These are not a compliance check.
- **Sampled headroom:** choose an overhead-object collection and run the measurement. Results are samples, not a continuous clearance guarantee. Rerun after overhead objects move.
- **Surface intersections:** choose a clash-object collection. The tool checks intersecting surfaces; complete containment, near misses and intentional contacts require manual review. Rerun after objects move.
- **SVG plan:** a schematic projection with visible and hidden edges; add dimensions and clean the drawing in your drafting workflow.
- **SVG section:** set the source object's local X section offset. The source needs unit scale and an upright local Z axis. Coplanar faces and drawing conventions need manual review.
- **Draft View / Restore View:** temporarily switch generated parts to bounding-box viewport display and restore their prior display settings. This does not change render geometry.

## Quantities

Use **Quantities (BOQ) → Calculate Quantities**, then **Export BOQ (CSV)**. Results depend on model geometry and assumptions. Per-material volumes are omitted if the corresponding shell is open or inconsistently oriented; overlapping geometry and estimation formulas still need independent checking. Recalculate after edits and verify all quantities against the project documents.

## Troubleshooting

- **Panel missing:** select the source mesh and confirm the add-on is enabled; generated child meshes are not the source.
- **Nothing generated:** inspect the selected mesh, engine, dimensions and the latest build error in Stair Stats.
- **Railing on the wrong edge:** check Edit Mode selection, edge markings, wall-detection settings and the source mesh. Rebuild after changes.
- **No headroom or clash result:** choose a collection containing relevant obstacle meshes, then run the corresponding check again.
- **Missing section:** move the section X offset so the cut plane intersects the stair and check the source object's scale and orientation.
- **Unexpected behaviour:** copy the full traceback from the terminal that launched Blender, note the Blender version and steps to reproduce, and test with a simple file.

No IFC authoring or validated BIM exchange is included. Exported drawings and quantities require review by the responsible project professionals.
