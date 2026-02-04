# ADR 006: Profile Metadata and Tracking System

## Status

Accepted

## Context

The mpv-controller API allows users to apply profiles to mpv instances, but there was no way to track which profiles were currently active on each instance. This created several problems:

1. **State Visibility**: Clients couldn't determine which profiles were applied without manually tracking applications
2. **Profile Stacking**: When multiple profiles were applied, there was no indication of the order or which ones were active
3. **Reset Semantics**: No standard way to indicate whether a profile should replace or add to existing configurations
4. **Type Confusion**: Profiles managing different aspects (shaders vs. settings) were treated identically, making it difficult to implement intelligent reset logic

The mpv profile system itself doesn't provide a way to query which profiles have been applied - it only shows the resulting configuration state (e.g., active shaders). This meant clients had to maintain their own state tracking or repeatedly query the full configuration.

## Decision

We will implement a profile tracking system with required metadata fields that:

1. **Add metadata fields to all profiles** using the `x-` prefix convention (fields mpv ignores):
   - `x-profile-type`: Indicates what the profile manages (`shader` or `setting`)
   - `x-profile-mode`: Indicates application behavior (`reset` or `additive`)

2. **Track applied profiles** in the API:
   - Maintain a per-instance list of applied profiles
   - Implement type-specific reset logic (shader profiles don't affect setting profiles)
   - Return tracked profiles in all status responses via `applied_profiles` field

3. **Validate metadata** at profile creation/update time:
   - Require both metadata fields on all profiles
   - Reject profiles with invalid metadata values
   - Provide clear error messages for missing/invalid metadata

4. **Version the API** as 0.2.0 to indicate the breaking change (profiles now require metadata)

### Metadata Contract

#### x-profile-type

Indicates what aspect of mpv configuration the profile affects.

**Values:**
- `shader`: Profile manages GLSL shaders (glsl-shaders-append, glsl-shaders-clr)
- `setting`: Profile manages other mpv settings (vf, af, volume, etc.)

**Extensibility:** Additional types can be added in the future (e.g., `audio`, `video-filter`, `subtitle`) without breaking existing functionality.

#### x-profile-mode

Indicates how the profile interacts with previously applied profiles.

**Values:**
- `reset`: Removes all previously tracked profiles of the same `x-profile-type` before applying this profile
- `additive`: Adds to existing tracked profiles of the same `x-profile-type`

### Profile Tracking Algorithm

```python
def track_applied_profile(instance_id, profile_name, profile_type, profile_mode):
    if profile_mode == RESET:
        # Remove all profiles of the same type
        applied_profiles[instance_id] = [
            (name, type) for name, type in applied_profiles[instance_id]
            if type != profile_type
        ]
    
    # Add the new profile
    applied_profiles[instance_id].append((profile_name, profile_type))
```

This allows:
- Shader profiles to reset other shader profiles without affecting settings
- Setting profiles to reset other setting profiles without affecting shaders
- Mixed stacking of different profile types
- Clear semantics for "clearing" configurations of a specific type

## Consequences

### Positive

1. **State Visibility**: Clients can now see which profiles are active via the `applied_profiles` field in status responses
2. **Intelligent Reset**: Type-specific reset prevents accidentally clearing unrelated configurations
3. **Better UX**: Clear indication of profile application order
4. **Extensible**: New profile types can be added without breaking changes
5. **mpv Compatible**: Using `x-` prefix ensures mpv ignores these fields
6. **Self-Documenting**: Profile metadata makes configuration intent clear

### Negative

1. **Breaking Change**: All existing profiles must be updated with metadata fields
2. **Migration Required**: Users upgrading from 0.1.x must update their profiles configuration
3. **Validation Overhead**: Every profile operation requires metadata validation
4. **Tracking State**: API must maintain additional state per instance

### Migration Path

Users upgrading from 0.1.x to 0.2.0 must:

1. Add `x-profile-type` and `x-profile-mode` to all existing profiles
2. Choose appropriate values based on what each profile manages
3. Update any profile creation/update API calls to include metadata

Example migration:
```ini
# Before (0.1.x)
[anime4k]
glsl-shaders-clr
glsl-shaders-append=~~/shaders/Anime4K.glsl

# After (0.2.0)
[anime4k]
x-profile-type=shader
x-profile-mode=reset
glsl-shaders-clr
glsl-shaders-append=~~/shaders/Anime4K.glsl
```

## Alternatives Considered

### 1. Track Without Metadata

Simply track all profile applications without any reset logic.

**Rejected because:**
- Couldn't implement intelligent reset semantics
- No way to know when to clear previous profiles
- Would accumulate profiles indefinitely

### 2. Use Profile Name Conventions

Use naming patterns like `shader-*` or `setting-*` to infer type.

**Rejected because:**
- Fragile and error-prone
- Restricts naming flexibility
- Not self-documenting
- Difficult to enforce

### 3. Separate Endpoints by Type

Have `/profiles/shaders` and `/profiles/settings` endpoints.

**Rejected because:**
- More complex API surface
- Doesn't solve the reset/additive distinction
- Harder to list all profiles
- Awkward for mixed-type workflows

### 4. Query mpv State Directly

Try to infer applied profiles by querying mpv configuration.

**Rejected because:**
- mpv doesn't expose which profiles were applied
- Multiple profiles can result in identical state
- Lossy reconstruction of application order
- Performance overhead from repeated queries

## Implementation Notes

- Metadata validation occurs in `ProfileManager._parse_profiles_config()`
- Profile tracking happens in `SocketManager.track_applied_profile()`
- Applied profiles included in `MpvState.applied_profiles`
- Protobuf updated to include `applied_profiles` field in gRPC API
- API version bumped from 0.1.0 to 0.2.0

## References

- [PROFILE_TRACKING_PLAN.md](../../PROFILE_TRACKING_PLAN.md) - Detailed implementation plan
- [mpv Manual - Profiles](https://mpv.io/manual/master/#profiles) - mpv profile documentation
- [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) - Key words for use in RFCs (MUST, SHOULD, etc.)
