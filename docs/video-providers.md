# Video providers

## Motion render

`MotionRenderVideoProvider` converts one validated hero image into a real MP4
using a deterministic HyperFrames timeline. Supported presets are deliberately
small: gentle push-in, slow pan, editorial short, and warm memory. The image stays the
visual anchor; a blurred cover layer may fill the vertical background while
the original image remains intact in the foreground.

The adapter runs the following local checks before returning an artifact:

1. HyperFrames lint.
2. HyperFrames validate.
3. HyperFrames inspect.
4. HyperFrames render.
5. FFprobe structure and stream validation.
6. SHA-256 and provenance materialization.

The final artifact records `video_generation_mode=MOTION_RENDER`. This means a
real video was rendered from a still image; it does not mean a model animated
the subject into new physical motion.

## Generative image-to-video

`GenerativeVideoProvider` is an interface boundary only in Phase 2R.
`GENERATIVE_I2V` is not implemented and is not required for the Phase gate.
Provider research lives in
`docs/research/GENERATIVE_I2V_REALITY_20260811.md`.

## Safety boundary

The renderer accepts local files and an optional external brand configuration.
It has no publisher, upload, OAuth, account, or remote-write path. Imported
images and rendered videos still require human review.
