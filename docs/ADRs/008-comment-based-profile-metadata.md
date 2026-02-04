# ADR 008: Comment-Based Profile Metadata

**Status**: Accepted  
**Date**: 2026-02-04  
**Deciders**: @jamesbrayton

## Context

Profile tracking requires custom metadata fields (`x-profile-type`, `x-profile-mode`) to determine reset vs additive behavior. Initially, these were implemented as regular mpv options with `x-` prefix (which mpv typically ignores).

**Problem discovered**: mpv exhibited finicky behavior with these fields - sometimes accepting them, sometimes rejecting profiles that contained them. This created an unreliable user experience where profiles would fail to apply unpredictably.

## Decision

**Move metadata to comments**: Write `x-profile-type` and `x-profile-mode` as comment lines (`#x-profile-type=shader`) instead of regular options.

**Tolerant parsing**: Profiles without metadata comments are silently skipped by the API rather than causing errors.

## Implementation

**Parser changes** (`profile_manager.py`):
- Added regex pattern to extract metadata from comment lines: `#\s*(x-profile-(?:type|mode))\s*=\s*(.+)`
- Changed validation from raising `ProfileConfigError` to logging debug messages and filtering out profiles without metadata
- Metadata can appear anywhere within a profile section (beginning, middle, or end)

**Serializer changes**:
- Metadata written as comments at the end of each profile (after all regular mpv options)
- Format: `#x-profile-type=shader` (no spaces around `=`)

**Migration**:
```bash
sed -i.backup 's/^x-profile-type=/#x-profile-type=/' profiles.conf
sed -i.backup 's/^x-profile-mode=/#x-profile-mode=/' profiles.conf
```

## Consequences

**Positive**:
- mpv completely ignores metadata - eliminates all parsing issues
- Profiles with and without metadata can coexist in same file
- Users can have "untracked" profiles that mpv uses but API doesn't expose
- More resilient to mpv version differences

**Negative**:
- Existing profiles.conf files need one-time migration
- Metadata slightly less visible (comments vs regular fields)

**Test coverage**: All 178 tests pass, coverage improved to 84%

## Related

- ADR 006: Profile Metadata Tracking (original metadata design)
- ADR 007: Flexible Profile Type Validation (custom type support)
