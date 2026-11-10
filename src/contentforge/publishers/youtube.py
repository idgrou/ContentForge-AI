"""YouTube Data API v3 upload (free quota). pip install 'contentforge-ai[youtube]'.

Create an OAuth client of type "Desktop app" in Google Cloud Console, download the JSON and set
YOUTUBE_CLIENT_SECRETS. The first run opens a browser to sign in; the token is saved locally.
"""

from __future__ import annotations

from pathlib import Path

from ..seo import YOUTUBE_TITLE_LIMIT, truncate, youtube_tags
from .base import PublishResult

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


class YouTubePublisher:
    def __init__(self, client_secrets: str, token_file: str = "youtube_token.json"):
        self.client_secrets, self.token_file = client_secrets, token_file

    def _service(self):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        creds = None
        if Path(self.token_file).exists():
            creds = Credentials.from_authorized_user_file(self.token_file, SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                creds = InstalledAppFlow.from_client_secrets_file(self.client_secrets, SCOPES).run_local_server(port=0)
            Path(self.token_file).write_text(creds.to_json())
        return build("youtube", "v3", credentials=creds)

    def upload(self, video: Path, title: str, description: str, tags: list[str], shorts: bool = False,
               privacy: str = "private", language: str = "he", thumbnail: Path | None = None) -> PublishResult:
        """Uploads as private by default; switch to public in YouTube Studio after review."""
        try:
            from googleapiclient.http import MediaFileUpload

            if shorts and "#shorts" not in (title + description).lower():
                description = f"{description}\n\n#Shorts"
            yt = self._service()
            body = {
                "snippet": {"title": truncate(title, YOUTUBE_TITLE_LIMIT), "description": description[:5000],
                            "tags": youtube_tags(tags), "categoryId": "22", "defaultLanguage": language},
                "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
            }
            request = yt.videos().insert(part="snippet,status", body=body,
                                         media_body=MediaFileUpload(str(video), chunksize=8 * 1024 * 1024, resumable=True))
            response = None
            while response is None:
                _, response = request.next_chunk()
            vid = response["id"]
            if thumbnail:
                yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(str(thumbnail))).execute()
            return PublishResult("youtube", True, id=vid, url=f"https://youtu.be/{vid}")
        except Exception as exc:
            return PublishResult("youtube", False, error=str(exc))
