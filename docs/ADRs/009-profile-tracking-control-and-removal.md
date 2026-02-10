# ADR 009: Profile Tracking Control and Shader Removal

## Status

Accepted

## Context

The profile tracking system (ADR 006) tracks all applied profiles, including "clearing" profiles like `no-shaders` that reset the shader stack to empty. This created an undesirable situation:

1. **Clearing Profiles in List**: Applying `no-shaders` would show `["no-shaders"]` in `applied_profiles`, even though the intent is to have no shaders active
2. **Hybrid Profiles**: Many profiles do `glsl-shaders-clr` followed by `glsl-shaders-append`, which is semantically "reset then add" but could only be marked as `reset` (clearing other profiles but staying in the list)
3. **No Undo**: Once an additive profile was applied, there was no way to remove it without applying a full reset profile

These limitations made it harder to achieve clean profile state management, particularly for experimental shader combinations where users want to add and remove individual effects.

## Decision

We will extend the profile metadata system with three enhancements:

### 1. Optional Tracking Control: `x-profile-track`

Add a new **optional** metadata field to control whether a profile appears in `applied_profiles`:

```ini
[no-shaders]
#x-profile-type=shader
#x-profile-mode=reset
#x-profile-track=false
glsl-shaders-clr
```

**Behavior:**
- Default: `true` (existing behavior - all profiles are tracked)
- When `false`: Profile applies and executes reset logic,  but doesn't add itself to the list
- Result: Clearing profiles leave `applied_profiles` empty for that type

**Use Cases:**
- Clearing profiles (`no-shaders`, `vf-off`) that should not appear in the list
- Temporary profiles for debugging that shouldn't affect tracking
- Profiles that are "state resets" rather than "configurations"

### 2. Dual-Mode Profiles: `reset,additive`

Extend `ProfileMode` enum to support hybrid behavior:

```python
class ProfileMode(str, Enum):
    RESET = "reset"
    ADDITIVE = "additive"
    RESET_ADDITIVE = "reset,additive"
```

**Syntax:** `#x-profile-mode=reset,additive`

**Behavior:**
1. Clear all profiles of the same type (reset phase)
2. Add this profile to the list (additive phase)
3. Result: `applied_profiles` contains **only** this profile for its type

**Use Cases:**
- Profiles that do `glsl-shaders-clr` then `glsl-shaders-append` (most shader profiles)
- Ensures clean state - no leftover profiles from previous applications
- Natural semantic for "replace all shaders with this specific set"

**Validation:** Only `reset,additive` order is accepted (not `additive,reset`)

### 3. Shader Profile Removal: DELETE Endpoint

Add new endpoint to remove previously applied shader profiles:

```
DELETE /instances/{instance_id}/profiles/{profile_name}
```

**Implementation:**
1. Verify profile is in `applied_profiles` (404 if not)
2. Verify profile type is `shader` (400 for other types)
3. Parse profile to extract `glsl-shaders-append` values
4. Send `change-list glsl-shaders remove <shader>` for each shader (reverse order)
5. Remove profile from tracking list
6. Return updated state

**Limitations:**
- **Shader-only**: Only shader profiles can be removed (non-shader profiles would require state snapshots)
- **Best-effort**: Partial failures return 502 with details of which shaders failed
- **Profile-dependent**: Removal depends on profile file content at removal time

**Use Cases:**
- Remove experimental additive effects (`bloom`, `chromatic-aberration`)
- Build custom shader stacks iteratively by adding/removing profiles
- Clean up after testing without full reset

## Consequences

### Positive

1. **Clean State**: Clearing profiles no longer clutter `applied_profiles` list
2. **Accurate Tracking**: List reflects actual active configurations, not reset operations
3. **Flexible Composition**: Dual-mode profiles provide both replacement and addition semantics
4. **Experimentation**: Users can add and remove shader profiles without full resets
5. **Backward Compatible**: Existing profiles continue working (new fields are optional or add-only)

### Negative

1. **Increased Complexity**: Three profile modes instead of two
2. **Partial Removal**: Shader removal is best-effort and may partially fail
3. **Type Limitation**: Only shader profiles can be removed (not settings)
4. **Fragile Removal**: Removal depends on profile file matching applied state

### Design Alternatives Considered

**Multiple `x-profile-mode` lines:**
```ini
#x-profile-mode=reset
#x-profile-mode=additive
```
- **Rejected**: Unusual pattern, order-dependent, more verbose

**Implicit behavior** based on profile name (`no-*`, `*-off`):
- **Rejected**: Violates ADR 006 decision against name conventions, fragile

**Change reset semantics** (reset means don't track):
- **Rejected**: Breaking change for existing profiles, loses visibility into resets

**Snapshot-based undo** (track full mpv state):
- **Rejected**: Complex, memory-intensive, persistence issues, scope creep

## Implementation

1. **Models**: Add `RESET_ADDITIVE` to `ProfileMode`, add `track: bool` to `ProfileInfo`
2. **Parser**: Extend regex to match `x-profile-track`, accept `reset,additive` mode
3. **Tracking**: Update `track_applied_profile()` to handle dual-mode and track flag
4. **REST API**: Add DELETE endpoint with shader-specific logic
5. **Validation**: Accept three mode values, parse track field with default `true`
6. **Migration**: Add `#x-profile-track=false` to clearing profiles in `profiles.conf`
7. **Version**: Bump to 0.4.0 (minor version for new features)

## Migration

**Existing profiles**: Continue working without changes (track defaults to `true`)

**New clearing profiles**: Add `#x-profile-track=false` to profiles like:
```ini
[no-shaders]
#x-profile-track=false
```

**Hybrid profiles**: Optionally convert to `#x-profile-mode=reset,additive` for clearer semantics

No breaking changes - all enhancements are additive or opt-in.

## Related

- ADR 006: Original profile tracking system
- ADR 007: Flexible profile type validation
- ADR 008: Comment-based profile metadata
