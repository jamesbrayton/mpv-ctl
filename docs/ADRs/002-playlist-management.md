# ADR-002: Playlist Management Implementation

## Status
Accepted

## Context
Users need the ability to manage playlists and switch between them. We needed to decide on the storage format, API design, and playlist switching behavior.

## Decision

### Storage Format
We chose M3U playlist format:
- Industry-standard format supported by mpv and most media players
- Simple text-based format that's easy to parse and generate
- Supports optional EXTINF metadata for entry titles
- Files stored in a configurable folder (`paths.playlist_folder`)

### API Design
Full CRUD operations for playlist files:
- List all playlists in the configured folder
- Get playlist contents by name
- Create new playlist with entries
- Update playlist (append or replace mode)
- Delete playlist

### Playlist Switching Modes
Three modes for switching to a new playlist on an mpv instance:

1. **immediate**: Replace current playlist and start playing immediately
   - Uses mpv's `loadlist ... replace` command
   - Default behavior

2. **after_current**: Append playlist, plays after current video ends
   - Uses mpv's `loadlist ... append` command
   - Current video continues, new playlist added to queue

3. **after_playlist**: Append playlist to end of current playlist
   - Same mpv command as after_current
   - Semantic distinction for API clarity

### Entry Model
Each playlist entry has:
- `path` (required): Path to the media file
- `title` (optional): Human-readable title for display

## Consequences

### Positive
- Standard M3U format works with other tools and players
- Simple file-based storage is reliable and portable
- Multiple switching modes give users flexibility
- Append mode allows queue building

### Negative
- Limited to single folder for playlists (no nested folders)
- Playlist names restricted to alphanumeric, hyphens, and underscores
- No playlist shuffling or advanced playlist features in this version

## Alternatives Considered

1. **Database storage for playlists**
   - Rejected: M3U files are simpler and more portable

2. **XSPF playlist format**
   - Rejected: More complex XML format, M3U is simpler and widely supported

3. **Single playlist update mode (replace only)**
   - Rejected: Append mode is useful for building queues incrementally

4. **Playlist switching via playlist index**
   - Rejected: Name-based switching is more user-friendly and readable
