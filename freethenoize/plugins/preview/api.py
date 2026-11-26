from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel


class Text(BaseModel):
    text: str


def routes(svc, ctx) -> APIRouter:
    r = APIRouter()

    @r.post("")
    def resolve(body: Text):
        return svc.resolve(body.text)

    @r.get("/{name}")
    def audio(name: str, t: float = 0):
        try:
            chunks = svc.stream(Path(name).stem, max(t, 0))
        except KeyError:
            raise HTTPException(404)
        return StreamingResponse(chunks, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})

    return r
