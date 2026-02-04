# ADR 007: Flexible Profile Type Validation

**Status:** Accepted  
**Date:** 2026-02-04

## Context

Profile metadata includes `x-profile-type` to categorize profiles and enable type-specific reset behavior. Initially, this field was validated against a hardcoded enum (`shader`, `setting`), requiring code changes to support new profile categories like video filters (`vf`), audio outputs (`ao`), or other mpv configuration domains.

## Decision

Allow any string value for `x-profile-type` while maintaining strict validation for `x-profile-mode`:

- **`x-profile-type`**: Accept any string value - only validate existence, not content
- **`x-profile-mode`**: Continue validating against `["reset", "additive"]` (behavioral requirement)

Reset behavior matches profiles by type string - applying a profile with `x-profile-mode=reset` and `x-profile-type=vf` clears all previously applied profiles where `x-profile-type=vf`.

## Consequences

**Positive:**
- Users can create custom profile types (`vf`, `ao`, etc.) without code modifications
- Type-based reset logic remains flexible and extensible
- Simpler codebase - no enum maintenance required

**Negative:**
- No compile-time validation of type values (typos possible but isolated in scope)
- Documentation must clearly explain type string usage

**Implementation:**
- Removed `ProfileType` enum from models
- Changed `ProfileInfo.profile_type` from `ProfileType` to `str`
- Removed validation checking type values in `ProfileManager._parse_profiles_config()`
- Updated all tests to use string literals instead of enum values
