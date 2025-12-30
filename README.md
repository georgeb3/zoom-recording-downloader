# Zoom Recording Downloader

A Python script to automatically download Zoom cloud recordings using the Zoom API. The script supports long-running downloads with automatic token refresh, tracks downloaded files via a manifest system, and organizes recordings by date and meeting topic.

## Features

- **Automatic Token Refresh**: Handles token expiration during long-running downloads (tokens expire after ~1 hour)
- **Manifest System**: Tracks downloaded files to avoid re-downloading on subsequent runs
- **Organized Storage**: Files are organized by date and meeting topic
- **Multiple File Types**: Supports MP4, M4A, CHAT, VTT, TRANSCRIPT, and other recording file types
- **Resume Capability**: Can resume interrupted downloads by skipping already-downloaded files
- **Configurable Time Range**: Download recordings from a specified number of months back

## Requirements

- Python 3.11 or higher
- `requests` library
- Zoom Server-to-Server OAuth app with appropriate scopes

## Installation

1. Clone or download this repository
2. Install the required dependency:

```bash
pip install requests
```

## Zoom API Setup

Before using this script, you need to create a Server-to-Server OAuth app in the Zoom Marketplace:

1. Go to [Zoom Marketplace](https://marketplace.zoom.us/)
2. Create a new Server-to-Server OAuth app
3. Enable the following scopes in your app settings:
   - `cloud_recording:read:list_user_recordings`
   - `cloud_recording:read:list_user_recordings:admin`
4. Note down your:
   - Account ID
   - Client ID
   - Client Secret

## Configuration

The script uses environment variables for configuration. Set the following:

### Required Environment Variables

- `ZOOM_ACCOUNT_ID`: Your Zoom account ID
- `ZOOM_CLIENT_ID`: Your OAuth app Client ID
- `ZOOM_CLIENT_SECRET`: Your OAuth app Client Secret
- `ZOOM_OUT_DIR`: Output directory for downloaded recordings

### Optional Environment Variables

- `ZOOM_USER_ID`: User ID to download recordings for (default: `"me"` - uses account owner)
  - Can be `"me"`, a Zoom user ID, or an email address
- `ZOOM_MONTHS_BACK`: Number of months to look back for recordings (default: `24`)

## Usage

### Basic Usage

Set the required environment variables and run the script:

```bash
export ZOOM_ACCOUNT_ID="your_account_id"
export ZOOM_CLIENT_ID="your_client_id"
export ZOOM_CLIENT_SECRET="your_client_secret"
export ZOOM_OUT_DIR="./zoom_recordings"
python3 zoom_recording_downloader.py
```

### Inline Environment Variables

You can also set environment variables inline:

```bash
ZOOM_ACCOUNT_ID="your_account_id" \
ZOOM_CLIENT_ID="your_client_id" \
ZOOM_CLIENT_SECRET="your_client_secret" \
ZOOM_OUT_DIR="./recordings" \
ZOOM_USER_ID="me" \
ZOOM_MONTHS_BACK="12" \
python3 zoom_recording_downloader.py
```

### Using a Specific User

To download recordings for a specific user:

```bash
ZOOM_ACCOUNT_ID="your_account_id" \
ZOOM_CLIENT_ID="your_client_id" \
ZOOM_CLIENT_SECRET="your_client_secret" \
ZOOM_OUT_DIR="./zoom_recordings" \
ZOOM_USER_ID="user@example.com" \
python3 zoom_recording_downloader.py
```

## Output Structure

Recordings are organized in the following structure:

```
output_directory/
├── manifest.json
└── YYYY-MM-DDTHH-MM-SS - Meeting Topic/
    └── meeting_id/
        ├── MP4.mp4
        ├── M4A.m4a
        ├── CHAT.txt
        ├── VTT.vtt
        └── TRANSCRIPT.vtt
```

### Manifest File

The `manifest.json` file tracks all downloaded files to prevent re-downloading. It contains:
- File keys (meeting_id:file_id:filename)
- Save location
- Download timestamp
- Date range information

## How It Works

1. **Authentication**: Gets an access token using Server-to-Server OAuth
2. **Time Windows**: Breaks the time range into month-sized windows for efficient API calls
3. **Listing**: Fetches all recordings for each time window
4. **Manifest Check**: Skips files that are already in the manifest
5. **Download**: Downloads each new recording file
6. **Token Refresh**: Automatically refreshes expired tokens during long-running downloads
7. **Progress Tracking**: Updates the manifest after each successful download

## Token Refresh

The script automatically handles token expiration:
- Detects 401 errors with code 124 (expired token)
- Refreshes the token using stored credentials
- Retries the failed operation with the new token
- Works for both API calls and download URLs

## Error Handling

- Failed downloads are logged but don't stop the script
- Token refresh errors will stop execution
- API errors are displayed with error codes and messages

## Troubleshooting

### "Invalid access token, does not contain scopes"

**Solution**: Ensure your Zoom OAuth app has the required scopes enabled:
- `cloud_recording:read:list_user_recordings`
- `cloud_recording:read:list_user_recordings:admin`

### "User does not exist"

**Solution**: Check that `ZOOM_USER_ID` is set correctly. Use `"me"` for the account owner, or a valid user ID/email.

### "Access token is expired"

**Solution**: This should be handled automatically by the token refresh mechanism. If you see this error, it may indicate an issue with the refresh callback.

### Download Failures

- Check your internet connection
- Verify the output directory is writable
- Ensure you have sufficient disk space
- Check Zoom API rate limits (the script includes pacing to avoid rate limits)

## File Types

The script handles various Zoom recording file types:
- **MP4**: Video recordings
- **M4A**: Audio-only recordings
- **CHAT**: Chat transcripts (saved as .txt)
- **VTT**: Video transcripts
- **TRANSCRIPT**: Transcript files (saved as .vtt)

## Limitations

- Requires a Zoom account with cloud recording enabled
- Server-to-Server OAuth apps have rate limits
- Large downloads may take significant time
- Token refresh requires valid credentials throughout the download process

## License

This script is provided as-is for personal or organizational use.

## Contributing

Feel free to submit issues or pull requests for improvements.

