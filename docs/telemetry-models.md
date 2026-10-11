# Animated language mix

The README features a compact 1000-unit-wide animated Language Mix (`assets/telemetry-3d.svg`). Six languages use a 490-unit-high canvas; ten use 686 units. Fewer entries use fewer rows. The Developer Workspace, laptop, terminal and browser have been removed, including their geometry, materials and animations. The language heading now sits at the top of the artwork, with no empty space reserved for the removed scene.

Language Mix requests the top ten languages and shows every returned entry, using two columns and up to five generously spaced rows. Each row has a 28-unit language logo, 26-unit name, 28-unit percentage and visible top/front/end faces. Logos from the local `scripts/language-icons.svg` library are embedded in the generated SVG; an unfamiliar language receives a code-file icon without blocking automatic updates. Active rail widths are literal percentages of a 392-unit track; a 0% language has no colored segment. Icons, labels and percentages stay upright and stationary throughout the animation. The footer contains only `UPDATED` and the retrieval timestamp.

No chip packages, commit/star/PR/issue counters, contribution blocks, flame or trophy remain. The self-contained dark background keeps the rails readable in either GitHub theme.

## Data refresh

```sh
python -B scripts/build_telemetry_models.py
```

The generator fetches and validates the language distribution from GitHub Readme Stats before writing anything. Percentages, source URL and retrieval time are saved in `assets/telemetry-data.json`. The SVG and its README/snippet cache hashes are then updated. Failed source responses leave the previous complete snapshot in place. The removed activity/streak services no longer block language refreshes. Service caching means retrieval time is not necessarily the latest GitHub data time.

```sh
python -B scripts/build_telemetry_models.py --offline
```

This command rebuilds the geometry from the saved dataset without fetching data or advancing the timestamp.

The `Refresh 3D telemetry stage` GitHub Actions workflow runs every six hours, on manual dispatch, and when its generator or workflow changes on `main`. It publishes the generated stage, data snapshot, README and preview layout by amending the single root commit on `main`. A force-with-lease push rejects concurrent remote changes; it never creates a second branch. No unused contribution graph workflows remain. It requires Actions to be enabled and repository content write permission; protected branches may prevent its direct push. Scheduled runs can be delayed by GitHub. See [GitHub workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax) and [scheduled event behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

Until the workflow is pushed to the default branch and runs successfully, the README displays the snapshot generated locally. It is not a continuously polling client. The UPDATED timestamp makes this explicit.

## Rendering & Animation

`docs/telemetry-layout.html` displays the full-width animated language mix linked to the user's repositories tab. The README and snippet use the comment `ANIMATED LANGUAGE MIX` and language-only image descriptions. No external frames, dividing rules, card borders, HUD corner ticks or neon dashed-lines are used.

Each language rail floats by 7 units and tilts by 1° in a 6-second cycle, offset by 0.65 seconds from the next rail. Shadows soften with the lift, while a 5.4-second reflection sweeps strictly within each colored segment. The horizontal active width stays constant, preserving the literal percentage. Names, percentages and timestamp never animate. With `prefers-reduced-motion`, all CSS animations stop and moving reflections disappear, leaving the complete static scene.

Run `python -B -m unittest discover -s scripts -p test_telemetry_models.py` to verify source parsing, offline timestamp preservation, language-only snapshots, valid SVG geometry and local references, removal of the workspace and old statistics models, rail clipping, language proportions including 0/100% boundaries, top-ten layout and icon fallback, and matching README/preview cache hashes. Browser previews should also be inspected at README width and phone width, sampling a complete animation cycle for clipping, label collisions and changed proportions. Verify motion and reduced motion in both inline SVG and the actual README image embedding.
