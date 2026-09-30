"""Authenticated host worker adapter. Ordinary user feature and data gates still apply."""
from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field


class MentionQuestion(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    question: str = Field(min_length=1)
    messageId: str = Field(min_length=1, max_length=200)


def install(app, runtime, gate):
    from semantic_bridge import access

    @app.post('/api/v1/chat/mention-answer')
    def answer(body: MentionQuestion, request: Request):
        # A separate local service credential never reaches the browser or chat messages.
        if not request.client or request.client.host not in ('127.0.0.1', '::1'):
            raise HTTPException(403, 'Local worker required')
        try:
            key = Path(os.environ.get('ZEKI_MENTION_KEY_FILE', '/etc/nanobase/zeki-mention.key')).read_text().strip()
        except OSError:
            key = ''
        supplied = request.headers.get('x-zeki-mention-key', '')
        if len(key) < 32 or not hmac.compare_digest(key, supplied):
            raise HTTPException(401, 'Worker authentication required')
        user = body.username.strip().lower()
        verdict, _ = gate('POST', '/api/v1/ask', user, access.rule_for('/api/v1/ask'),
                          access.features_for('POST', '/api/v1/ask'), True, lambda *_: None)
        if verdict:
            raise HTTPException(verdict[0], verdict[1])
        question = body.question.strip()
        if not question:
            raise HTTPException(422, 'Soru boş.')
        # Each request has its own context: no other member's previous answer enters this prompt.
        thread = 'chat-' + hashlib.sha256((user + ':' + body.messageId).encode()).hexdigest()
        with access.acting_as(user):
            return runtime().ask(question, thread_id=thread, sample_size=50, execute=True, username=user)
