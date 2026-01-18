# ADR-005: Installation and Upgrade Handling

## Status
Accepted

## Context
Users need to be able to install mpv-controller and also upgrade existing installations without data loss or manual intervention. The installation script needed to handle both fresh installs and upgrades gracefully.

## Decision

### Upgrade Detection
The install script detects existing installations by checking for the installation directory at `~/.local/share/mpv-controller`.

### Interactive vs Non-Interactive Modes

1. **Interactive (terminal)**: When an existing installation is detected and stdin is a terminal:
   - Prompts user for confirmation before proceeding
   - User can choose to upgrade or cancel

2. **Non-interactive (piped)**: When script is piped (e.g., `curl | bash`):
   - Automatically upgrades existing installation
   - No prompt since stdin is not available for user input

3. **Explicit upgrade flag**: For scripted deployments with explicit intent:
   - `./install.sh main --upgrade`
   - Proceeds with upgrade without prompting regardless of terminal state

### Upgrade Process

1. Stop the running systemd service (if active)
2. Remove the old virtual environment (`.venv` directory)
3. Create a fresh virtual environment
4. Install the new package version
5. Preserve user configuration (config.yaml is never overwritten)
6. Reload systemd daemon
7. Provide restart instructions

### Configuration Preservation
- Existing `config.yaml` is never modified during upgrades
- New config options can be added manually by users
- Example config shows all available options for reference

### Service Handling
- Service is stopped before upgrade to prevent issues with changed dependencies
- User must manually restart the service after upgrade
- This provides opportunity to review any required config changes

## Consequences

### Positive
- Clean upgrades without leftover dependencies
- User configuration preserved across upgrades
- Interactive mode prevents accidental overwrites
- Non-interactive mode enables automated deployments
- Service state is handled gracefully

### Negative
- User must manually restart service after upgrade
- New config options require manual addition
- Complete venv recreation may be slower than incremental update

## Alternatives Considered

1. **In-place pip upgrade**
   - Rejected: Can leave orphaned dependencies, potential version conflicts

2. **Automatic service restart after upgrade**
   - Rejected: Gives users opportunity to review changes before restart

3. **Automatic config migration**
   - Rejected: Risk of breaking user customizations, adds complexity

4. **Backup before upgrade**
   - Considered for future: Would add safety but also complexity
