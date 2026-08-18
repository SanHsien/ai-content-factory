# Voice providers

The core owns provider-neutral `VoiceProfile`, `VoiceArtifact`, selection, and
provenance contracts. A private brand layer owns the actual voice identity,
style approval, and engine configuration.

The offline demo uses a fixture descriptor. `LocalCommandVoiceProvider` is an
explicit adapter for a configured local executable; it is not automatically
discovered and it does not bundle an engine, voice model, or voice asset.

The base demo can run without narration. A contributed engine must declare its
license, model source, language support, network behavior, voice rights,
determinism limits, and failure mode. Missing engines must produce an
actionable error rather than silently selecting a private voice.
