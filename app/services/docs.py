import uuid

def create_or_update_google_doc_mock(user_id: int, content: str) -> str:
    return f"https://docs.google.com/document/d/mock-{user_id}-{uuid.uuid4().hex[:8]}/edit"
