#!/usr/bin/env python3
"""
YouTube Live Stream Downloader and Re-uploader
Downloads a YouTube live stream and uploads it as a regular video.
"""

import os
import sys
import argparse
import logging
from pathlib import Path
import yt_dlp
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

# YouTube API scopes
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

class YouTubeStreamProcessor:
    def __init__(self, credentials_file='credentials.json', token_file='token.json'):
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.youtube = None
        self.logger = self._setup_logging()
        
    def _setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        return logging.getLogger(__name__)
    
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
                    self.logger.error(f"Credentials file {self.credentials_file} not found")
                    self.logger.error("Please download your OAuth 2.0 credentials from Google Cloud Console")
                    return False
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file, SCOPES)
                creds = flow.run_local_server(port=0)
            
            with open(self.token_file, 'w') as token:
                token.write(creds.to_json())
        
        self.youtube = build('youtube', 'v3', credentials=creds)
        return True
    
    def download_stream(self, stream_url, output_path='./downloads'):
        """Download YouTube live stream"""
        self.logger.info(f"Starting download of stream: {stream_url}")
        
        # Create output directory if it doesn't exist
        Path(output_path).mkdir(parents=True, exist_ok=True)
        
        # Configure yt-dlp options
        ydl_opts = {
            'outtmpl': f'{output_path}/%(title)s.%(ext)s',
            'format': 'best[ext=mp4]/best',
            'writeinfojson': True,  # Save metadata
            'writethumbnail': True,  # Save thumbnail
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract info first
                info = ydl.extract_info(stream_url, download=False)
                
                if info.get('is_live'):
                    self.logger.warning("Stream is currently live. Downloading live streams may be incomplete.")
                
                # Download the video
                ydl.download([stream_url])
                
                # Return the downloaded file path
                filename = ydl.prepare_filename(info)
                return filename, info
                
        except Exception as e:
            self.logger.error(f"Error downloading stream: {str(e)}")
            return None, None
    
    def upload_video(self, video_file, title=None, description=None, tags=None, 
                    category_id='22', privacy_status='private'):
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
            'snippet': {
                'title': title or f"Re-uploaded Stream - {Path(video_file).stem}",
                'description': description or "Video downloaded from live stream and re-uploaded.",
                'tags': tags or ['livestream', 'reupload'],
                'categoryId': category_id
            },
            'status': {
                'privacyStatus': privacy_status
            }
        }
        
        # Create media upload object
        media = MediaFileUpload(
            video_file,
            chunksize=-1,
            resumable=True,
            mimetype='video/*'
        )
        
        try:
            # Execute the upload
            insert_request = self.youtube.videos().insert(
                part=','.join(body.keys()),
                body=body,
                media_body=media
            )
            
            response = None
            error = None
            retry = 0
            
            while response is None:
                try:
                    status, response = insert_request.next_chunk()
                    if status:
                        self.logger.info(f"Upload progress: {int(status.progress() * 100)}%")
                except HttpError as e:
                    if e.resp.status in [500, 502, 503, 504]:
                        error = f"A retriable HTTP error {e.resp.status} occurred:\n{e.content}"
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
                video_id = response.get('id')
                self.logger.info(f"Upload successful! Video ID: {video_id}")
                self.logger.info(f"Video URL: https://www.youtube.com/watch?v={video_id}")
                return video_id
            
        except HttpError as e:
            self.logger.error(f"HTTP error occurred: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Error uploading video: {str(e)}")
            return None
    
    def process_stream(self, stream_url, output_path='./downloads', 
                      upload_title=None, upload_description=None, 
                      upload_tags=None, privacy_status='private'):
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
        
        # Step 3: Prepare upload metadata from downloaded info
        if info:
            title = upload_title or f"Re-upload: {info.get('title', 'Unknown Title')}"
            description = upload_description or f"Original description:\n{info.get('description', 'No description available')}"
            tags = upload_tags or info.get('tags', ['livestream', 'reupload'])
        else:
            title = upload_title or f"Re-uploaded Stream - {Path(video_file).stem}"
            description = upload_description or "Video downloaded from live stream and re-uploaded."
            tags = upload_tags or ['livestream', 'reupload']
        
        # Step 4: Upload the video
        video_id = self.upload_video(
            video_file=video_file,
            title=title,
            description=description,
            tags=tags,
            privacy_status=privacy_status
        )
        
        if video_id:
            self.logger.info("Process completed successfully!")
            return True
        else:
            self.logger.error("Upload failed")
            return False

def main():
    parser = argparse.ArgumentParser(description='Download YouTube live stream and re-upload as regular video')
    parser.add_argument('stream_url', help='YouTube live stream URL')
    parser.add_argument('--output-path', default='./downloads', help='Output directory for downloads')
    parser.add_argument('--credentials', default='credentials.json', help='OAuth credentials file')
    parser.add_argument('--token', default='token.json', help='OAuth token file')
    parser.add_argument('--title', help='Custom title for uploaded video')
    parser.add_argument('--description', help='Custom description for uploaded video')
    parser.add_argument('--tags', nargs='*', help='Custom tags for uploaded video')
    parser.add_argument('--privacy', choices=['private', 'public', 'unlisted'], 
                       default='private', help='Privacy status for uploaded video')
    parser.add_argument('--download-only', action='store_true', 
                       help='Only download, do not upload')
    
    args = parser.parse_args()
    
    processor = YouTubeStreamProcessor(
        credentials_file=args.credentials,
        token_file=args.token
    )
    
    if args.download_only:
        video_file, info = processor.download_stream(args.stream_url, args.output_path)
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
            privacy_status=args.privacy
        )
        
        if not success:
            sys.exit(1)

if __name__ == '__main__':
    main()