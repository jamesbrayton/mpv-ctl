# Profile Tracking Implementation Plan

## Overview

Add profile tracking functionality to mpv-controller API to return currently applied profiles in status responses. This enables clients to understand which named profiles are active on each mpv instance.

## Problem Statement

Currently, the status endpoint returns the runtime state (e.g., active shaders array) but doesn't indicate which named profiles were applied to achieve that state. This makes it difficult for clients to:
- Know which profiles are currently active
- Understand the application order when multiple profiles are stacked
- Manage profile state across API calls

## Solution

Implement a profile tracking system using required metadata fields in profiles that the API reads but mpv ignores (using `x-` prefix convention). Track applied profiles per instance and return them in status responses.

## Metadata Contract

All profiles must include two required metadata fields:

### x-profile-type
Indicates what aspect of mpv configuration the profile affects.

**Values:**
- `shader` - Profile manages GLSL shaders (glsl-shaders-append, glsl-shaders-clr)
- `setting` - Profile manages other mpv settings (vf, af, etc.)

**Extensibility:** Additional types can be added in the future (e.g., `audio`, `video-filter`) without breaking changes.

### x-profile-mode
Indicates how the profile interacts with previously applied profiles.

**Values:**
- `reset` - Removes all previously tracked profiles of the same `x-profile-type` before applying this profile
- `additive` - Adds to existing tracked profiles of the same `x-profile-type`

**Example Profile Format:**
```ini
[anime4k-medium]
x-profile-type=shader
x-profile-mode=reset
profile-desc=Anime4K Medium Quality
glsl-shaders-clr
glsl-shaders-append=~~/shaders/Anime4K_Upscale_L.glsl
glsl-shaders-append=~~/shaders/Anime4K_Auto_Downscale.glsl

[debanding]
x-profile-type=setting
x-profile-mode=additive
profile-desc=Enable debanding filter
vf=gradfun=radius=16

[none]
x-profile-type=shader
x-profile-mode=reset
profile-desc=Clear all shaders
glsl-shaders-clr
```

## Implementation Steps

### 1. Define Enums in models.py

Create two new Enum classes for profile metadata:

```python
class ProfileType(str, Enum):
    """Type of profile indicating what it manages."""
    SHADER = "shader"
    SETTING = "setting"

class ProfileMode(str, Enum):
    """Mode of profile application."""
    RESET = "reset"
    ADDITIVE = "additive"
```

### 2. Extend ProfileInfo Model

**File:** `mpv_controller/models.py`

Add metadata fields to ProfileInfo:

```python
class ProfileInfo(BaseModel):
    """Information about an mpv profile."""
    
    name: str = Field(...)
    options: dict[str, Any] = Field(default_factory=dict)
    profile_type: ProfileType = Field(
        ...,
        description="Type of profile (shader or setting)"
    )
    profile_mode: ProfileMode = Field(
        ...,
        description="Application mode (reset or additive)"
    )
```

Update ProfileCreateRequest and ProfileUpdateRequest to require validation of the metadata fields in the options dict.

### 3. Update ProfileManager Parsing

**File:** `mpv_controller/profile_manager.py`

Modify `_parse_profiles_config()` to:
1. Extract `x-profile-type` and `x-profile-mode` from profile options
2. Validate they exist and have valid values
3. Convert to ProfileType and ProfileMode enums
4. Raise ProfileConfigError with descriptive message if missing or invalid

Example error messages:
- `"Profile 'anime4k' missing required field 'x-profile-type'"`
- `"Profile 'anime4k' has invalid x-profile-type value 'invalid'. Must be 'shader' or 'setting'"`

Update `create_profile()` and `update_profile()` to validate metadata fields before saving.

### 4. Add Profile Tracking to SocketManager

**File:** `mpv_controller/socket_manager.py`

Add instance variable in `__init__`:
```python
self._applied_profiles: dict[str, list[tuple[str, ProfileType]]] = {}
```

Implement new method:
```python
def track_applied_profile(
    self,
    instance_id: str,
    profile_name: str,
    profile_type: ProfileType,
    profile_mode: ProfileMode
) -> None:
    """Track applied profile with type-specific reset logic.
    
    Args:
        instance_id: ID of the mpv instance
        profile_name: Name of the applied profile
        profile_type: Type of profile (shader or setting)
        profile_mode: Application mode (reset or additive)
    """
    if instance_id not in self._applied_profiles:
        self._applied_profiles[instance_id] = []
    
    if profile_mode == ProfileMode.RESET:
        # Remove all profiles of the same type
        self._applied_profiles[instance_id] = [
            (name, ptype) 
            for name, ptype in self._applied_profiles[instance_id]
            if ptype != profile_type
        ]
    
    # Add the new profile
    self._applied_profiles[instance_id].append((profile_name, profile_type))
    
    logger.debug(
        "Tracked applied profile",
        instance_id=instance_id,
        profile=profile_name,
        type=profile_type,
        mode=profile_mode,
        current_profiles=[name for name, _ in self._applied_profiles[instance_id]]
    )

def get_applied_profiles(self, instance_id: str) -> list[str]:
    """Get list of currently applied profile names for an instance.
    
    Args:
        instance_id: ID of the mpv instance
        
    Returns:
        List of profile names in application order
    """
    if instance_id not in self._applied_profiles:
        return []
    return [name for name, _ in self._applied_profiles[instance_id]]
```

### 5. Update apply_profile Endpoint

**File:** `mpv_controller/rest_api.py`

Modify the `/mpv/{instance_id}/profile` endpoint to track profiles after successful application:

```python
async def apply_profile(...):
    """Apply a profile to an mpv instance."""
    logger.info("Apply profile", instance_id=instance_id, profile=profile_name)

    # Get profile with metadata
    profile = profile_manager.get_profile(profile_name)

    result = socket_manager.send_command(
        instance_id,
        ["apply-profile", profile_name],
    )
    
    # Track the applied profile if command was successful
    if result.get("error") == "success":
        socket_manager.track_applied_profile(
            instance_id,
            profile_name,
            profile.profile_type,
            profile.profile_mode
        )

    state = socket_manager.get_standard_state(instance_id)

    return CommandResponse(...)
```

### 6. Extend MpvState Model

**File:** `mpv_controller/models.py`

Add field to MpvState:

```python
class MpvState(BaseModel):
    """State information from mpv instance."""
    
    # ... existing fields ...
    
    applied_profiles: Optional[list[str]] = Field(
        None,
        description="List of currently applied profile names in application order",
        examples=[["anime4k-medium", "debanding"]],
    )
```

### 7. Update get_standard_state Method

**File:** `mpv_controller/socket_manager.py`

Modify `get_standard_state()` to include applied profiles:

```python
def get_standard_state(self, instance_id: str) -> MpvState:
    """Get standard state properties from an mpv instance.
    
    Args:
        instance_id: ID of the mpv instance to query.
        
    Returns:
        MpvState object with current state.
    """
    state_dict = {}
    
    for prop in STANDARD_PROPERTIES:
        # ... existing property fetching logic ...
    
    # Add applied profiles
    state_dict["applied_profiles"] = self.get_applied_profiles(instance_id)
    
    return MpvState(**state_dict)
```

### 8. Normalize Shader Arrays in Profile Responses

**File:** `mpv_controller/profile_manager.py`

In `get_profile()` and `list_profiles()`, convert `glsl-shaders-append` string values to single-item arrays:

```python
def get_profile(self, name: str) -> ProfileInfo:
    """Get a specific profile by name."""
    # ... existing code ...
    
    # Normalize shader values to arrays
    if "glsl-shaders-append" in options:
        value = options["glsl-shaders-append"]
        if isinstance(value, str):
            options["glsl-shaders-append"] = [value]
    
    return ProfileInfo(
        name=name,
        options=options,
        profile_type=profile_type,
        profile_mode=profile_mode
    )
```

### 9. Increment API Version

**File:** `mpv_controller/rest_api.py`

Change version from `"0.1.0"` to `"0.2.0"`:

```python
app = FastAPI(
    title="mpv Controller API",
    description="REST API for controlling multiple mpv instances via Unix sockets",
    version="0.2.0",  # Changed from 0.1.0
    docs_url="/docs" if config.server.enable_swagger_ui else None,
    redoc_url="/redoc" if config.server.enable_swagger_ui else None,
)
```

## Behavior Examples

### Example 1: Reset Shader Profile
```
Initial state: applied_profiles = []

Apply profile "anime4k-medium" (type=shader, mode=reset):
Result: applied_profiles = ["anime4k-medium"]

Apply profile "debanding" (type=setting, mode=additive):
Result: applied_profiles = ["anime4k-medium", "debanding"]

Apply profile "none" (type=shader, mode=reset):
Result: applied_profiles = ["debanding"]
```

### Example 2: Additive Shader Profile
```
Initial state: applied_profiles = ["anime4k-medium"]

Apply profile "sharpen" (type=shader, mode=additive):
Result: applied_profiles = ["anime4k-medium", "sharpen"]

Apply profile "tone-mapping" (type=setting, mode=reset):
Result: applied_profiles = ["anime4k-medium", "sharpen", "tone-mapping"]
```

## Status Response Example

```json
{
  "command_result": {
    "success": true,
    "data": null,
    "error": null
  },
  "state": {
    "pause": false,
    "time_pos": 123.45,
    "duration": 1800.0,
    "filename": "/path/to/video.mkv",
    "volume": 75.0,
    "speed": 1.0,
    "mute": false,
    "glsl_shaders": [
      "/path/to/shader1.glsl",
      "/path/to/shader2.glsl"
    ],
    "applied_profiles": [
      "anime4k-medium",
      "debanding"
    ]
  },
  "instance_id": "mpv-0"
}
```

## Error Handling

### Missing Metadata Fields
When a profile is missing required metadata:
```
ProfileConfigError: Profile 'anime4k' missing required field 'x-profile-type'
```

### Invalid Metadata Values
When metadata has invalid values:
```
ProfileConfigError: Profile 'anime4k' has invalid x-profile-type value 'shader-filter'. Must be 'shader' or 'setting'
```

## Migration Notes

1. **Existing Profiles:** All existing profiles must be updated to include `x-profile-type` and `x-profile-mode` fields before the service can start after upgrading.

2. **Profile Order:** The `applied_profiles` list maintains insertion order, with most recently applied profiles appearing last.

3. **mpv Compatibility:** The `x-` prefix ensures mpv ignores these metadata fields, so they are API-only and don't affect mpv behavior.

## Future Extensibility

### Adding New Profile Types
New profile types can be added by:
1. Adding value to `ProfileType` enum
2. No changes needed to tracking logic (type-specific reset already implemented)

Example future types:
- `audio` - Audio processing settings
- `video-filter` - Video filter chain settings
- `subtitle` - Subtitle rendering settings

### Adding New Profile Modes
If additional modes are needed beyond reset/additive:
1. Add to `ProfileMode` enum
2. Update `track_applied_profile()` logic to handle new mode
3. Document behavior

## Testing Checklist

- [ ] Profile with `x-profile-type=shader` and `x-profile-mode=reset` clears other shader profiles
- [ ] Profile with `x-profile-type=setting` and `x-profile-mode=reset` clears other setting profiles
- [ ] Profile with `mode=reset` only clears profiles of the same type
- [ ] Profile with `mode=additive` appends to existing list
- [ ] Status endpoint returns correct `applied_profiles` list
- [ ] Profiles without metadata fields raise ProfileConfigError
- [ ] Profiles with invalid metadata values raise ProfileConfigError
- [ ] Profile tracking persists across multiple API calls
- [ ] Multiple profiles can be stacked additively
- [ ] API version is incremented to 0.2.0

## Files to Modify

1. `mpv_controller/models.py` - Add enums and extend ProfileInfo, MpvState
2. `mpv_controller/profile_manager.py` - Add metadata parsing and validation
3. `mpv_controller/socket_manager.py` - Add profile tracking logic
4. `mpv_controller/rest_api.py` - Update apply_profile endpoint and version
5. `config.example.yaml` - Update example profiles with metadata (optional)
6. `README.md` - Document new profile metadata requirements (optional)

## Implementation Order

1. Add enums to models.py
2. Extend ProfileInfo model
3. Update ProfileManager parsing
4. Add tracking to SocketManager
5. Update apply_profile endpoint
6. Extend MpvState model
7. Update get_standard_state
8. Normalize shader arrays
9. Increment version
10. Test thoroughly

## Success Criteria

- Status endpoint returns list of applied profile names
- Profiles can be stacked additively
- Reset mode correctly clears profiles of the same type
- API validates all profiles have required metadata
- No breaking changes to existing API endpoints (except profiles now require metadata)
- Version incremented to 0.2.0
