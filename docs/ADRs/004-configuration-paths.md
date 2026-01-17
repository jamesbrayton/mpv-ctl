# ADR-004: Configuration Paths Structure

## Status
Accepted

## Context
The new profile and playlist management features require configuration paths to be specified. We needed to decide how to structure this configuration and handle cases where paths are not configured.

## Decision

### Configuration Structure
Added a new `paths` section to the configuration:

```yaml
paths:
  mpv_config_path: ~/.config/mpv/mpv.conf      # Optional, for future use
  profiles_config_path: ~/.config/mpv/profiles.conf
  playlist_folder: ~/playlists
```

### Path Handling
1. **Path expansion**: All paths support `~` for home directory expansion via Python's `os.path.expanduser()`

2. **Optional configuration**: All path settings are optional
   - If not configured, the corresponding feature returns a configuration error
   - Service still starts and other features work normally

3. **Graceful degradation**: Missing path configuration results in clear error messages
   - HTTP 503 with `PROFILE_CONFIG_ERROR` or `PLAYLIST_CONFIG_ERROR`
   - Error message explains what needs to be configured

4. **Directory creation**: Services create directories as needed
   - Playlist folder created when first playlist is created
   - Profile file's parent directory created when first profile is created

### Default Values
All path settings default to `None` (not configured):
- Allows existing users to upgrade without breaking changes
- Forces explicit configuration of new features
- Clear error when feature is used without configuration

## Consequences

### Positive
- Backward compatible - existing configs work without changes
- Clear separation between mpv instance config and file path config
- Flexible - users can put files wherever they want
- Graceful error handling with clear messages

### Negative
- New users must configure paths to use profile/playlist features
- No "smart defaults" (e.g., auto-detecting mpv config location)
- Each feature requires separate path configuration

## Alternatives Considered

1. **Auto-detect mpv config locations**
   - Rejected: Too magic, different users have different setups

2. **Single "data directory" setting**
   - Rejected: Less flexible, forces specific directory structure

3. **Environment variable override for paths**
   - Rejected for now: Can be added later if needed; YAML config is sufficient

4. **Required path configuration**
   - Rejected: Would break existing users on upgrade; features should be opt-in
