# YouTube Live Stream Downloader and Re-uploader

A Python script that downloads YouTube live streams and uploads them as regular YouTube videos using the YouTube API.

## Features

- Download YouTube live streams using yt-dlp
- Authenticate with YouTube API using OAuth 2.0
- Upload downloaded videos as regular YouTube videos
- Preserve original metadata (title, description, tags, thumbnails)
- Resume interrupted uploads
- Configurable privacy settings
- Progress tracking and detailed logging
- Error handling and retry logic

## Requirements

- Python 3.7+
- YouTube Data API v3 credentials
- Required Python packages (see requirements.txt)

## Installation

1. Clone or download this repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up YouTube API credentials:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select existing one
   - Enable the YouTube Data API v3
   - Create OAuth 2.0 credentials (Desktop application)
   - Download the credentials JSON file
   - Save it as `credentials.json` in the project directory

## Usage

### Basic Usage

Download a stream and upload it as a regular video:
```bash
python youtube_stream_reupload.py "https://www.youtube.com/watch?v=STREAM_ID"
```

### Download Only

Download the stream without uploading:
```bash
python youtube_stream_reupload.py "https://www.youtube.com/watch?v=STREAM_ID" --download-only
```

### Custom Options

```bash
python youtube_stream_reupload.py "https://www.youtube.com/watch?v=STREAM_ID" \
  --title "My Custom Title" \
  --description "Custom description for the video" \
  --tags "tag1" "tag2" "tag3" \
  --privacy "public" \
  --output-path "./my_downloads"
```

### Command Line Arguments

- `stream_url` (required): YouTube live stream URL
- `--output-path`: Directory for downloaded files (default: ./downloads)
- `--credentials`: OAuth credentials file path (default: credentials.json)
- `--token`: OAuth token file path (default: token.json)
- `--title`: Custom title for uploaded video
- `--description`: Custom description for uploaded video
- `--tags`: Custom tags for uploaded video (space-separated)
- `--privacy`: Privacy status - private, public, or unlisted (default: private)
- `--download-only`: Only download, don't upload

## Authentication

On first run, the script will:
1. Open your web browser for OAuth authentication
2. Ask you to sign in to your Google account
3. Request permissions to upload videos to YouTube
4. Save authentication tokens for future use

The authentication tokens are saved in `token.json` and will be automatically refreshed when needed.

## File Structure

After running the script, you'll have:
```
project-directory/
├── youtube_stream_reupload.py  # Main script
├── requirements.txt            # Python dependencies
├── credentials.json           # OAuth credentials (you provide)
├── token.json                # OAuth tokens (auto-generated)
├── downloads/                # Downloaded videos directory
│   ├── video_title.mp4       # Downloaded video file
│   ├── video_title.info.json # Video metadata
│   └── video_title.webp      # Video thumbnail
```

## Privacy and Security

- Videos are uploaded as **private** by default for safety
- OAuth tokens are stored locally in `token.json`
- Never share your `credentials.json` or `token.json` files
- The script only requests upload permissions, not read access to your account

## Troubleshooting

### Common Issues

1. **"Credentials file not found"**
   - Download OAuth credentials from Google Cloud Console
   - Save as `credentials.json` in project directory

2. **"API quota exceeded"**
   - YouTube API has daily quotas
   - Wait 24 hours or request quota increase

3. **"Video upload failed"**
   - Check internet connection
   - Verify video file isn't corrupted
   - Try uploading as private first

4. **"Stream is currently live"**
   - Live streams may download incompletely
   - Wait for stream to end for best results

### Debug Mode

For detailed logging, modify the logging level in the script:
```python
logging.basicConfig(level=logging.DEBUG)
```

## Limitations

- YouTube API quotas limit daily uploads
- Large video files may take time to upload
- Live streams may be incomplete if downloaded while streaming
- Some streams may be protected and unable to download

## Legal Notice

This tool is for personal use and educational purposes. Ensure you have permission to download and re-upload content. Respect YouTube's Terms of Service and copyright laws.

## License

This project is provided as-is for educational purposes. Use responsibly and in accordance with YouTube's Terms of Service.