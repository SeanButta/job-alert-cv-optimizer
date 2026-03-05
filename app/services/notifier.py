def build_alert(job_title: str, link: str, score: float, doc_url: str) -> str:
    return f"Match found: {job_title} (score={score:.2f})\nJob link: {link}\nCV doc: {doc_url}"

def send_mock(channel: str, target: str, message: str) -> dict:
    return {'channel': channel, 'target': target, 'status': 'mock_sent', 'message': message}
