#!/usr/bin/env python3
"""
YouTube Live Stream Downloader and Re-uploader
Downloads a YouTube live stream and uploads it as a regular video.
"""

import argparse
import hashlib
import logging
import os
import sys
from pathlib import Path

import yt_dlp
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

# YouTube API scopes
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


class YouTubeStreamProcessor:
    def __init__(self, credentials_file="credentials.json", token_file="token.json"):
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.youtube = None
        self.logger = self._setup_logging()

    def _setup_logging(self):
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
        )
        return logging.getLogger(__name__)

    def list_playlists(self):
        """List all playlists for the authenticated channel"""
        if not self.youtube:
            if not self.authenticate_youtube():
                return []

        try:
            playlists = []
            request = self.youtube.playlists().list(
                part="snippet", mine=True, maxResults=50
            )

            while request is not None:
                response = request.execute()

                for playlist in response["items"]:
                    playlists.append(
                        {
                            "id": playlist["id"],
                            "title": playlist["snippet"]["title"],
                            "description": playlist["snippet"].get("description", ""),
                        }
                    )

                request = self.youtube.playlists().list_next(request, response)

            return playlists

        except Exception as e:
            self.logger.error(f"Error listing playlists: {e}")
            return []

    def find_playlist_by_name(self, search_term):
        """Find playlist by searching for a term in the title"""
        playlists = self.list_playlists()
        search_term_lower = search_term.lower()

        matches = []
        for playlist in playlists:
            if search_term_lower in playlist["title"].lower():
                matches.append(playlist)

        return matches

    def _calculate_file_hash(self, filepath, chunk_size=8192):
        """Calculate SHA-256 hash of a file"""
        hash_sha256 = hashlib.sha256()
        try:
            with open(filepath, "rb") as f:
                for chunk in iter(lambda: f.read(chunk_size), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        except Exception as e:
            self.logger.warning(f"Could not calculate hash for {filepath}: {e}")
            return None

    def _verify_file_integrity(self, filepath, expected_filesize=None):
        """Verify file exists, has reasonable size, and is not corrupted"""
        if not os.path.exists(filepath):
            return False

        file_stats = os.path.stat(filepath)

        # Check if file is empty
        if file_stats.st_size == 0:
            self.logger.warning(f"File {filepath} is empty")
            return False

        # Check if file size matches expected (if provided)
        if expected_filesize and abs(file_stats.st_size - expected_filesize) > (
            expected_filesize * 0.05
        ):
            self.logger.warning(
                f"File size mismatch for {filepath}. Expected: {expected_filesize}, Got: {file_stats.st_size}"
            )
            return False

        # Try to read the file to ensure it's not corrupted
        try:
            with open(filepath, "rb") as f:
                f.read(1024)  # Read first 1KB to check if file is readable
            return True
        except Exception as e:
            self.logger.warning(f"File {filepath} appears corrupted: {e}")
            return False

    def authenticate_youtube(self):
        """Authenticate with YouTube API"""
        creds = None

        if os.path.exists(self.token_file):
            creds = Credentials.from_authorized_user_file(self.token_file, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.credentials_file):
                    self.logger.error(
                        f"Credentials file {self.credentials_file} not found"
                    )
                    self.logger.error(
                        "Please download your OAuth 2.0 credentials from Google Cloud Console"
                    )
                    return False

                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file, SCOPES
                )
                creds = flow.run_local_server(port=0)

            with open(self.token_file, "w") as token:
                token.write(creds.to_json())

        self.youtube = build("youtube", "v3", credentials=creds)
        return True

    def download_stream(self, stream_url, output_path="./downloads"):
        """Download YouTube live stream"""
        self.logger.info(f"Starting download of stream: {stream_url}")

        # Create output directory if it doesn't exist
        Path(output_path).mkdir(parents=True, exist_ok=True)

        # Configure yt-dlp options
        ydl_opts = {
            "outtmpl": f"{output_path}/%(title)s.%(ext)s",
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/bestvideo+bestaudio/best",
            "writeinfojson": True,  # Save metadata
            "writethumbnail": True,  # Save thumbnail
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract info first
                info = ydl.extract_info(stream_url, download=False)

                if info.get("is_live"):
                    self.logger.warning(
                        "Stream is currently live. Downloading live streams may be incomplete."
                    )

                # Check if video already exists and verify integrity
                filename = ydl.prepare_filename(info)
                expected_filesize = info.get("filesize") or info.get("filesize_approx")

                if os.path.exists(filename):
                    if self._verify_file_integrity(filename, expected_filesize):
                        self.logger.info(
                            f"Video already exists and is valid: {filename}"
                        )
                        return filename, info
                    else:
                        self.logger.info(
                            f"Existing file is corrupted or incomplete, re-downloading: {filename}"
                        )
                        # Remove the corrupted file
                        try:
                            os.remove(filename)
                        except Exception as e:
                            self.logger.warning(
                                f"Could not remove corrupted file {filename}: {e}"
                            )

                # Download the video
                ydl.download([stream_url])

                # Return the downloaded file path
                return filename, info

        except Exception as e:
            self.logger.error(f"Error downloading stream: {str(e)}")
            return None, None

    def upload_video(
        self,
        video_file,
        title=None,
        description=None,
        tags=None,
        category_id="28",
        privacy_status="private",
        thumbnail_file=None,
        recording_date=None,
        default_language=None,
        default_audio_language=None,
        playlist_id=None,
    ):
        """Upload video to YouTube"""
        if not self.youtube:
            self.logger.error("YouTube API not authenticated")
            return None

        if not os.path.exists(video_file):
            self.logger.error(f"Video file not found: {video_file}")
            return None

        self.logger.info(f"Starting upload of: {video_file}")

        # Prepare video metadata
        body = {
            "snippet": {
                "title": title or f"Re-uploaded Stream - {Path(video_file).stem}",
                "description": description
                or "Video downloaded from live stream and re-uploaded.",
                "tags": tags or [],
                "categoryId": category_id,
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False,
            },
        }

        # Add recording date if provided (format: YYYY-MM-DDTHH:MM:SS.sssZ)
        if recording_date:
            try:
                # Convert YYYYMMDD format to ISO 8601 format
                if len(recording_date) == 8 and recording_date.isdigit():
                    formatted_date = f"{recording_date[:4]}-{recording_date[4:6]}-{recording_date[6:8]}T00:00:00.000Z"
                    body["recordingDetails"] = {"recordingDate": formatted_date}
            except Exception:
                self.logger.warning(
                    f"Invalid recording date format: {recording_date}. Skipping recording date."
                )

        # Set default languages to English if not specified
        body["snippet"]["defaultLanguage"] = (
            default_language
            if (default_language and len(default_language) <= 5)
            else "en"
        )
        body["snippet"]["defaultAudioLanguage"] = (
            default_audio_language
            if (default_audio_language and len(default_audio_language) <= 5)
            else "en"
        )

        # Create media upload object
        media = MediaFileUpload(
            video_file, chunksize=-1, resumable=True, mimetype="video/mp4"
        )

        try:
            # Execute the upload
            insert_request = self.youtube.videos().insert(
                part=",".join(body.keys()), body=body, media_body=media
            )

            response = None
            retry = 0

            while response is None:
                try:
                    status, response = insert_request.next_chunk()
                    if status:
                        self.logger.info(
                            f"Upload progress: {int(status.progress() * 100)}%"
                        )
                except HttpError as e:
                    if e.resp.status in [500, 502, 503, 504]:
                        retry += 1
                        if retry > 5:
                            self.logger.error("Too many retries. Upload failed.")
                            return None
                    else:
                        raise
                except Exception as e:
                    self.logger.error(f"An unexpected error occurred: {e}")
                    return None

            if response:
                video_id = response.get("id")
                self.logger.info(f"Upload successful! Video ID: {video_id}")
                self.logger.info(
                    f"Video URL: https://www.youtube.com/watch?v={video_id}"
                )

                # Upload thumbnail if provided
                if thumbnail_file and os.path.exists(thumbnail_file):
                    self._upload_thumbnail(video_id, thumbnail_file)

                # Add to playlist if specified
                if playlist_id:
                    self._add_to_playlist(video_id, playlist_id)

                return video_id

        except HttpError as e:
            self.logger.error(f"HTTP error occurred: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Error uploading video: {str(e)}")
            return None

    def _upload_thumbnail(self, video_id, thumbnail_file):
        """Upload thumbnail for the video"""
        try:
            self.logger.info(f"Uploading thumbnail: {thumbnail_file}")

            # YouTube only supports JPEG and PNG thumbnails
            file_ext = thumbnail_file.lower().split(".")[-1]

            # If it's already a supported format, upload directly
            if file_ext in ["jpg", "jpeg", "png"]:
                mime_type = "image/jpeg" if file_ext in ["jpg", "jpeg"] else "image/png"
                self.youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(thumbnail_file, mimetype=mime_type),
                ).execute()
                self.logger.info("Thumbnail uploaded successfully")
            else:
                # For unsupported formats (webp, gif, bmp), convert to JPEG
                self.logger.info(f"Converting unsupported format {file_ext} to JPEG")
                converted_path = self._convert_thumbnail_to_jpeg(thumbnail_file)
                if converted_path:
                    self.youtube.thumbnails().set(
                        videoId=video_id,
                        media_body=MediaFileUpload(
                            converted_path, mimetype="image/jpeg"
                        ),
                    ).execute()
                    self.logger.info("Converted thumbnail uploaded successfully")
                    # Clean up converted file
                    try:
                        os.remove(converted_path)
                    except Exception:
                        self.logger.warning(
                            f"Could not remove converted thumbnail {converted_path}"
                        )
                else:
                    self.logger.warning(
                        f"Could not convert thumbnail format {file_ext}"
                    )

        except Exception as e:
            self.logger.warning(f"Failed to upload thumbnail: {str(e)}")

    def _convert_thumbnail_to_jpeg(self, thumbnail_file):
        """Convert thumbnail to JPEG format using PIL if available, otherwise skip"""
        try:
            from PIL import Image

            # Generate output filename
            output_path = thumbnail_file.rsplit(".", 1)[0] + "_converted.jpg"

            # Open and convert image
            with Image.open(thumbnail_file) as img:
                # Convert to RGB if necessary (for formats like PNG with transparency)
                if img.mode in ("RGBA", "LA", "P"):
                    # Create white background for transparency
                    background = Image.new("RGB", img.size, (255, 255, 255))
                    if img.mode == "P":
                        img = img.convert("RGBA")
                    background.paste(
                        img,
                        mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None,
                    )
                    img = background
                elif img.mode != "RGB":
                    img = img.convert("RGB")

                # Save as JPEG
                img.save(output_path, "JPEG", quality=95, optimize=True)

            return output_path

        except ImportError:
            self.logger.warning(
                "PIL/Pillow not available. Cannot convert thumbnail format."
            )
            return None
        except Exception as e:
            self.logger.warning(f"Error converting thumbnail: {e}")
            return None

    def _add_to_playlist(self, video_id, playlist_id):
        """Add video to specified playlist"""
        try:
            self.logger.info(f"Adding video to playlist: {playlist_id}")
            self.youtube.playlistItems().insert(
                part="snippet",
                body={
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {"kind": "youtube#video", "videoId": video_id},
                    }
                },
            ).execute()
            self.logger.info("Video added to playlist successfully")
        except Exception as e:
            self.logger.warning(f"Failed to add video to playlist: {str(e)}")

    def process_stream(
        self,
        stream_url,
        output_path="./downloads",
        upload_title=None,
        upload_description=None,
        upload_tags=None,
        privacy_status="private",
        playlist_id=None,
        playlist_search=None,
    ):
        """Complete process: download stream and upload as regular video"""

        # Step 1: Download the stream
        video_file, info = self.download_stream(stream_url, output_path)

        if not video_file or not os.path.exists(video_file):
            self.logger.error("Failed to download stream")
            return False

        # Step 2: Authenticate with YouTube API
        if not self.authenticate_youtube():
            self.logger.error("Failed to authenticate with YouTube API")
            return False

        # Step 2.5: Handle playlist selection
        if playlist_search and not playlist_id:
            matches = self.find_playlist_by_name(playlist_search)
            if matches:
                # Default to "cybersec tuesday" if multiple matches, otherwise use first match
                cybersec_match = None
                for match in matches:
                    if (
                        "cybersec" in match["title"].lower()
                        and "tuesday" in match["title"].lower()
                    ):
                        cybersec_match = match
                        break

                selected_playlist = cybersec_match or matches[0]
                playlist_id = selected_playlist["id"]
                self.logger.info(
                    f"Found playlist: {selected_playlist['title']} (ID: {playlist_id})"
                )
            else:
                self.logger.warning(f"No playlists found matching '{playlist_search}'")

        # Step 3: Prepare upload metadata from downloaded info
        if info:
            title = upload_title or info.get("title", "Unknown Title")
            description = upload_description or info.get(
                "description", "No description available"
            )
            tags = upload_tags or info.get("tags", [])
            # Use default category ID as YouTube categories can be region/channel specific
            category_id = "28"  # Science & Technology
            recording_date = info.get("upload_date")
            default_language = info.get("language")
            # Find thumbnail file - check multiple possible extensions and locations
            thumbnail_file = None
            video_stem = Path(video_file).stem

            # Try common thumbnail extensions that yt-dlp might use
            thumbnail_extensions = ["jpg", "jpeg", "png", "webp"]
            for ext in thumbnail_extensions:
                thumbnail_path = f"{output_path}/{video_stem}.{ext}"
                if os.path.exists(thumbnail_path):
                    thumbnail_file = thumbnail_path
                    self.logger.info(f"Found thumbnail: {thumbnail_file}")
                    break

            if not thumbnail_file:
                self.logger.info("No thumbnail file found for upload")
        else:
            title = upload_title or f"Re-uploaded Stream - {Path(video_file).stem}"
            description = (
                upload_description
                or "Video downloaded from live stream and re-uploaded."
            )
            tags = upload_tags or []
            category_id = "28"
            recording_date = None
            default_language = None
            thumbnail_file = None

        # Step 4: Upload the video
        video_id = self.upload_video(
            video_file=video_file,
            title=title,
            description=description,
            tags=tags,
            category_id=category_id,
            privacy_status=privacy_status,
            thumbnail_file=thumbnail_file,
            recording_date=recording_date,
            default_language=default_language,
            playlist_id=playlist_id,
        )

        if video_id:
            self.logger.info("Process completed successfully!")
            return True
        else:
            self.logger.error("Upload failed")
            return False


def main():
    parser = argparse.ArgumentParser(
        description="Download YouTube live stream and re-upload as regular video"
    )
    parser.add_argument("stream_url", help="YouTube live stream URL")
    parser.add_argument(
        "--output-path", default="./downloads", help="Output directory for downloads"
    )
    parser.add_argument(
        "--credentials", default="credentials.json", help="OAuth credentials file"
    )
    parser.add_argument("--token", default="token.json", help="OAuth token file")
    parser.add_argument("--title", help="Custom title for uploaded video")
    parser.add_argument("--description", help="Custom description for uploaded video")
    parser.add_argument("--tags", nargs="*", help="Custom tags for uploaded video")
    parser.add_argument(
        "--privacy",
        choices=["private", "public", "unlisted"],
        default="private",
        help="Privacy status for uploaded video",
    )
    parser.add_argument("--playlist", help="Playlist ID to add video to")
    parser.add_argument(
        "--playlist-search",
        help='Search for playlist by name (e.g., "cybersec tuesday")',
    )
    parser.add_argument(
        "--list-playlists",
        action="store_true",
        help="List all available playlists and exit",
    )
    parser.add_argument(
        "--download-only", action="store_true", help="Only download, do not upload"
    )

    args = parser.parse_args()

    processor = YouTubeStreamProcessor(
        credentials_file=args.credentials, token_file=args.token
    )

    # Handle playlist listing
    if args.list_playlists:
        playlists = processor.list_playlists()
        if playlists:
            print("Available playlists:")
            for playlist in playlists:
                print(f"  ID: {playlist['id']}")
                print(f"  Title: {playlist['title']}")
                if playlist["description"]:
                    print(f"  Description: {playlist['description'][:100]}...")
                print()
        else:
            print("No playlists found or authentication failed")
        sys.exit(0)

    if args.download_only:
        video_file, _ = processor.download_stream(args.stream_url, args.output_path)
        if video_file:
            print(f"Download completed: {video_file}")
        else:
            print("Download failed")
            sys.exit(1)
    else:
        success = processor.process_stream(
            stream_url=args.stream_url,
            output_path=args.output_path,
            upload_title=args.title,
            upload_description=args.description,
            upload_tags=args.tags,
            privacy_status=args.privacy,
            playlist_id=args.playlist,
            playlist_search=args.playlist_search,
        )

        if not success:
            sys.exit(1)


if __name__ == "__main__":
    main()
