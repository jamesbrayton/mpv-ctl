# ADR-003: Speed and Frame Navigation Controls

## Status
Accepted

## Context
Users need fine-grained playback control including speed adjustment and frame-by-frame navigation. We needed to decide on the API design and step increments.

## Decision

### Speed Control Endpoints

1. **Set absolute speed**: `POST /mpv/{instance_id}/speed`
   - Body: `{"speed": 1.5}`
   - Accepts any value from 0.01 to 100 (mpv's valid range)
   - Uses mpv's `set_property speed` command

2. **Step up speed**: `POST /mpv/{instance_id}/speed/up`
   - Increases speed by 0.05
   - Uses mpv's `add speed 0.05` command

3. **Step down speed**: `POST /mpv/{instance_id}/speed/down`
   - Decreases speed by 0.05
   - Uses mpv's `add speed -0.05` command

### Frame Navigation Endpoints

1. **Frame forward**: `POST /mpv/{instance_id}/frame/forward`
   - Advances exactly one frame
   - Uses mpv's `frame-step` command
   - Automatically pauses playback (mpv behavior)

2. **Frame backward**: `POST /mpv/{instance_id}/frame/backward`
   - Goes back exactly one frame
   - Uses mpv's `frame-back-step` command
   - Automatically pauses playback (mpv behavior)

### Step Increment Choice (0.05)
Chose 0.05 as the speed step increment because:
- Standard increment used in many media players
- 20 steps from 1.0x to 2.0x (or 0.0x to 1.0x)
- Fine enough for precision, coarse enough for quick adjustment
- Matches mpv's default keybinding increment

## Consequences

### Positive
- Intuitive endpoint design (speed/up, speed/down)
- Fixed step size keeps API simple
- Frame navigation works as expected with mpv's behavior
- Speed range matches mpv's supported range

### Negative
- Step increment is not configurable (fixed at 0.05)
- Frame stepping pauses playback (mpv's inherent behavior)
- No "slow motion" shortcut endpoint (users can set speed directly)

## Alternatives Considered

1. **Configurable step increment**
   - Rejected: Adds complexity; users who need custom increments can use the absolute speed endpoint

2. **Combined speed endpoint with mode parameter**
   - Rejected: Separate endpoints are more RESTful and clearer in API documentation

3. **Frame count parameter (step N frames)**
   - Rejected: mpv's frame-step doesn't support this; would require a loop which could cause timing issues
