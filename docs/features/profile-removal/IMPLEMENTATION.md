# Profile Tracking Control and Removal - Implementation Notes

## Overview

Enhancement to profile management system adding:
1. Optional tracking control via `x-profile-track` metadata
2. Dual-mode profiles with `reset,additive` behavior 
3. DELETE endpoint for removing applied shader profiles

**Version:** 0.4.0  
**ADR:** 009 - Profile Tracking Control and Removal

## Implementation Summary

### 1. Models (`mpv_controller/models.py`)

Added to `ProfileMode` enum:
```python
RESET_ADDITIVE = "reset,additive"
```

Added to `ProfileInfo` model:
```python
track: bool = Field(
    True,
    description="Whether to track this profile in applied_profiles list (default: True)",
)
```

### 2. Profile Parser (`mpv_controller/profile_manager.py`)

**Regex update** to match `x-profile-track`:
```python
metadata_match = re.match(r"^#\s*(x-profile-(?:type|mode|track))\s*=\s*(.+)$", line)
```

**Validation** accepts three modes:
```python
if profile_mode_str not in ["reset", "additive", "reset,additive"]:
    raise ProfileConfigError(...)
```

**Parsing track field**:
```python
track = True
if "x-profile-track" in options:
    track_value = options["x-profile-track"].lower()
    track = track_value in ["true", "yes", "1"]
```

**Serialization** writes track metadata:
```python
if "x-profile-track" in options:
    lines.append(f"#x-profile-track={options['x-profile-track']}")
```

### 3. Socket Manager (`mpv_controller/socket_manager.py`)

**Updated signature**:
```python
def track_applied_profile(
    self,
    instance_id: str,
    profile_name: str,
    profile_type: str,
    profile_mode: ProfileMode,
    track: bool = True,
) -> None:
```

**Dual-mode handling**:
```python
if profile_mode in (ProfileMode.RESET, ProfileMode.RESET_ADDITIVE):
    # Clear profiles of same type
    self._applied_profiles[instance_id] = [
        (name, ptype)
        for name, ptype in self._applied_profiles[instance_id]
        if ptype != profile_type
    ]

# Only add if track=True
if track:
    self._applied_profiles[instance_id].append((profile_name, profile_type))
```

### 4. REST API (`mpv_controller/rest_api.py`)

**Updated apply_profile** to pass track field:
```python
socket_manager.track_applied_profile(
    instance_id,
    profile_name,
    profile.profile_type,
    profile.profile_mode,
    profile.track,  # New parameter
)
```

**New DELETE endpoint**:
```
DELETE /instances/{instance_id}/profiles/{profile_name}
```

Logic:
1. Check profile is applied (404 if not)
2. Validate type is `shader` (400 otherwise)
3. Extract `glsl-shaders-append` values from profile
4. Send `change-list glsl-shaders remove <shader>` for each (reverse order)
5. Remove from tracking list
6. Return updated state with removal status

Error handling:
- Tracks partial failures (some shaders may fail to remove)
- Returns 502 if any removals failed
- Still removes from tracking list even on failures

### 5. Configuration (`local/profiles.conf`)

Updated clearing profiles:
```ini
[no-shaders]
#x-profile-type=shader
#x-profile-mode=reset
#x-profile-track=false  # NEW
glsl-shaders-clr

[vf-off]
#x-profile-type=vf
#x-profile-mode=reset
#x-profile-track=false  # NEW
vf=
vf-clr=yes
```

## Usage Examples

### Clearing Profile (Not Tracked)

```bash
# Apply no-shaders
curl -X POST http://localhost:8000/instances/mpv-0/profiles?profile_name=no-shaders

# Check applied profiles
curl http://localhost:8000/instances/mpv-0/properties/applied_profiles
# Returns: []  (empty - no-shaders not tracked)
```

### Dual-Mode Profile

```ini
[nature-enhanced]
#x-profile-type=shader
#x-profile-mode=reset,additive
glsl-shaders-clr
glsl-shaders-append=~~/shaders/nature-pack.glsl
glsl-shaders-append=~~/shaders/denoise.glsl
```

```bash
# Apply after having other shaders
curl -X POST http://localhost:8000/instances/mpv-0/profiles?profile_name=anime4k
curl -X POST http://localhost:8000/instances/mpv-0/profiles?profile_name=nature-enhanced

# Check applied profiles  
curl http://localhost:8000/instances/mpv-0/properties/applied_profiles
# Returns: ["nature-enhanced"]  (anime4k was cleared by reset behavior)
```

### Removing Shader Profile

```bash
# Apply profiles
curl -X POST http://localhost:8000/instances/mpv-0/profiles?profile_name=nature
curl -X POST http://localhost:8000/instances/mpv-0/profiles?profile_name=bloom

# Remove bloom
curl -X DELETE http://localhost:8000/instances/mpv-0/profiles/bloom

# Check applied profiles
curl http://localhost:8000/instances/mpv-0/properties/applied_profiles
# Returns: ["nature"]  (bloom removed)
```

## Testing Considerations

### Unit Tests Needed

1. **Parser tests** (`test_profile_manager.py`):
   - Parse `x-profile-track=true/false`
   - Accept `reset,additive` mode value
   - Default track to true when omitted
   - Serialize track metadata

2. **Tracking tests** (`test_socket_manager.py`):
   - Dual-mode clears then adds
   - track=false doesn't add to list
   - track=true adds to list (existing behavior)

3. **REST API tests** (`test_rest_api.py`):
   - DELETE endpoint returns 404 if profile not applied
   - DELETE endpoint returns 400 for non-shader profiles
   - DELETE endpoint removes shaders in reverse order
   - DELETE endpoint updates tracking list
   - Apply endpoint passes track field

4. **Integration tests**:
   - End-to-end profile application with tracking
   - Profile removal with actual mpv instance

### Edge Cases

1. **Profile file changed after apply**: Removal may fail if shaders differ
2. **Partial shader removal failure**: Some shaders remove successfully, others fail
3. **Profile not in list**: DELETE returns 404
4. **Concurrent removals**: No locking, last writer wins
5. **Invalid track values**: Parser should handle "True", "TRUE", "1", "yes" case-insensitively

## Known Limitations

1. **Shader-only removal**: Only shader profiles can be removed (setting profiles require state snapshots)
2. **No undo history**: Can't restore previous state after removal
3. **File dependency**: Removal depends on profile file content at removal time
4. **Best-effort**: Shader removal may partially fail without transaction rollback
5. **No batch operations**: Must remove profiles one at a time

## Future Enhancements

1. **Batch removal**: DELETE multiple profiles in one operation
2. **Setting profile removal**: Implement state snapshots for non-shader profiles
3. **Profile history**: Maintain stack of previous states for undo/redo
4. **gRPC endpoint**: Add RemoveProfile RPC (required for API parity)
5. **Validation endpoint**: Check if profile can be removed before attempting

## Related Files

- `mpv_controller/models.py` - Data models
- `mpv_controller/profile_manager.py` - Profile parsing and management
- `mpv_controller/socket_manager.py` - Profile tracking logic
- `mpv_controller/rest_api.py` - REST API endpoints
- `local/profiles.conf` - Profile configuration
- `docs/ADRs/009-profile-tracking-control-and-removal.md` - Architecture decision

## Changelog

- **0.4.0**: Added `x-profile-track` metadata, `reset,additive` mode, DELETE endpoint for shader removal
