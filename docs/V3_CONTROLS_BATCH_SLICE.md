# Sprite Factory V3: Controls + Batch Slice

## Why this slice goes first

The current app already has good feature coverage, but two UI areas carry too much state inside widgets:

- the preview control strip repeats active-asset normalization logic
- the batch manager owns queue labels, statuses, progress text, and rerun selection rules directly in the dialog

Cleaning those two areas first gives us safer ground for the wider UI rebuild.

## What landed in this slice

- dedicated control-strip state normalization helper
- dedicated batch queue state helper for rows, failed-item tracking, and progress text
- current batch manager can now reselect failed items quickly after a run
- targeted tests cover the new helpers plus the failed-item rerun flow

## Rebuild direction

This is the intended migration path for the controls and batch surfaces:

1. Normalize UI-facing state in small helper/view-model modules.
2. Keep Qt widgets thin: render state, emit intent, avoid owning business rules.
3. Move batch execution and selection policies behind application-layer contracts.
4. Rebuild the controls surface as composable sections instead of one large settings wall.
5. Let v3 presentation consume the same state contracts before we cut over from v2.

## Next steps

- split the right-side settings panel into grouped sections with dedicated state mappers
- introduce a presentation-neutral batch run summary model for v3
- create a v3 workspace shell that can host the rebuilt controls and batch surfaces in parallel
- bridge the v3 presentation shell to the current controller until feature parity is ready
