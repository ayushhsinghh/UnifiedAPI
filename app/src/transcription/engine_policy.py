"""Enabled audio engines; independent from providers used by fact generation."""
DEFAULT_AUDIO_ENGINES = frozenset({'whisper', 'riva'})


def audio_engine_enabled(engine, config):
    return engine in getattr(config, 'AUDIO_TRANSCRIPTION_ENABLED_ENGINES', DEFAULT_AUDIO_ENGINES)
