# Editorial engine

The editorial engine turns a script into explicit visual and audio intent. Its
generic contracts include `EditorialPlan`, `ShotSpec`, `AssetPlanner`,
`DirectorPromptCompiler`, `SubtitleEditor`, `AudioEditor`,
`TimelineCompiler`, and `EditorialQualityScorecard`.

An editorial plan records target duration, platform, aspect ratio, pace,
story arc, shots, sources, camera intent, transitions, subtitles, audio, and
continuity. Quality rules reject long unchanged visuals, excessive text cards,
low shot density, repeated assets, and invalid transition timing.

The v0.1 offline demo emits a compact storyboard and media plan. Advanced
applications can compile full editorial plans into a renderer, but renderer
tools and brand styling remain optional. Generic rules belong in the core;
logos, colors, voice, private prompts, and real media belong in a private
profile supplied at runtime.
