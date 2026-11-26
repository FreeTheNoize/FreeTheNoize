from fastapi import APIRouter
from pydantic import BaseModel

from ...plugin import LibraryPath


class ConvertBody(BaseModel):
    files: list[LibraryPath]
    format: str
    out_dir: LibraryPath | None = None
    normalize_lufs: float | None = None


def routes(svc, ctx) -> APIRouter:
    r = APIRouter()

    @r.post("")
    def convert(body: ConvertBody):
        return svc.convert(body.files, body.format, body.out_dir, body.normalize_lufs)

    return r
