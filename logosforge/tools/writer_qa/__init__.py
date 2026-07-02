"""Writer QA harness — headless, deterministic writer/tester for LogosForge.

Drives the real Assistant contract layer (`logosforge.assistant_contract`)
with a deterministic fake provider across a section × mode × action × target ×
response scenario matrix, and emits actionable bug reports. No real provider,
network, cloud, GitHub, or DB access; writes only under the chosen report path.
"""
