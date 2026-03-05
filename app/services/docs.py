import os
import uuid
from typing import Optional


def create_or_update_google_doc_mock(user_id: int, content: str) -> str:
    return f"https://docs.google.com/document/d/mock-{user_id}-{uuid.uuid4().hex[:8]}/edit"


def create_or_update_google_doc(user_id: int, content: str, title: Optional[str] = None) -> str:
    """
    Real mode requires:
      ENABLE_REAL_GOOGLE_DOCS=true
      GOOGLE_SERVICE_ACCOUNT_JSON=/path/to/service-account.json
      GOOGLE_DOC_SHARE_WITH=<email> (optional)
    """
    if os.getenv('ENABLE_REAL_GOOGLE_DOCS', 'false').lower() != 'true':
        return create_or_update_google_doc_mock(user_id, content)

    creds_path = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON')
    if not creds_path or not os.path.exists(creds_path):
        return create_or_update_google_doc_mock(user_id, content)

    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    scopes = [
        'https://www.googleapis.com/auth/documents',
        'https://www.googleapis.com/auth/drive',
    ]
    creds = service_account.Credentials.from_service_account_file(creds_path, scopes=scopes)
    docs = build('docs', 'v1', credentials=creds)
    drive = build('drive', 'v3', credentials=creds)

    doc = docs.documents().create(body={'title': title or f'CV Recommendations - User {user_id}'}).execute()
    doc_id = doc['documentId']

    docs.documents().batchUpdate(
        documentId=doc_id,
        body={'requests': [{'insertText': {'location': {'index': 1}, 'text': content}}]},
    ).execute()

    share_email = os.getenv('GOOGLE_DOC_SHARE_WITH')
    if share_email:
        drive.permissions().create(
            fileId=doc_id,
            body={'type': 'user', 'role': 'writer', 'emailAddress': share_email},
            sendNotificationEmail=False,
        ).execute()

    return f'https://docs.google.com/document/d/{doc_id}/edit'
