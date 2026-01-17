# ADR-001: Profile Management Implementation

## Status
Accepted

## Context
Users need the ability to manage mpv profiles (groups of settings) through the API. mpv supports profiles via configuration files, and we needed to decide how to implement profile management in mpv-controller.

## Decision
We implemented profile management with the following approach:

1. **File-based storage**: Profiles are stored in a standard mpv profiles.conf file format
   - Maintains compatibility with mpv's native profile system
   - Users can edit profiles manually if desired
   - Location configured via `paths.profiles_config_path` in config.yaml

2. **INI-style format parsing**:
   - Profile sections denoted by `[profile-name]`
   - Options as `key=value` pairs
   - Boolean values (`yes`/`no`, `true`/`false`) automatically converted

3. **Full CRUD operations**:
   - List all profiles
   - Get profile details by name
   - Create new profile
   - Update profile (full replacement of options)
   - Delete profile

4. **Profile application via mpv IPC**:
   - Apply profiles to running instances using mpv's `apply-profile` command
   - Verifies profile exists before applying

## Consequences

### Positive
- Compatible with existing mpv profile workflows
- Users can manage profiles both via API and direct file editing
- Profiles persist across service restarts
- Leverages mpv's built-in profile application mechanism

### Negative
- Profile changes require API call or service restart to take effect in mpv
- Update operation replaces all options (no partial update)
- Profile file must be readable/writable by the service

## Alternatives Considered

1. **In-memory profiles**: Store profiles only in the service memory
   - Rejected: Would lose profiles on restart, incompatible with mpv's profile system

2. **Database storage**: Store profiles in SQLite or similar
   - Rejected: Over-engineered for this use case, adds dependency, incompatible with mpv native format

3. **mpv.conf integration**: Parse and modify mpv.conf directly
   - Rejected: More complex to parse, risk of corrupting user's main config
