"""Authenticated catalogue read service; independent of model workers and maintenance."""
from uuid import UUID
import hmac
import os
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from .presentation import cards, cover_path

def authorize(authorization: str = Header(default='')):
    expected=os.environ.get('EDITOR_CARDS_KEY','')
    if not expected or not hmac.compare_digest(authorization.removeprefix('Bearer ').strip(),expected):
        raise HTTPException(401,'unauthorized')

app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None,dependencies=[Depends(authorize)])

@app.get('/v1/books/cards')
def book_cards():
    return {'items':cards(),'read_only':True}

@app.get('/v1/books/{book_id}/cover')
def book_cover(book_id: UUID):
    try:
        path,source=cover_path(str(book_id))
        return FileResponse(path,headers={'Cache-Control':'private, no-cache','X-Cover-Source':source})
    except KeyError:
        raise HTTPException(404,'cover not found') from None
