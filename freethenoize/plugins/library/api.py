from fastapi import APIRouter
from fastapi.responses import FileResponse, Response

from ...plugin import LibraryPath


def routes(svc, ctx) -> APIRouter:
    r = APIRouter()

    @r.get("")
    def listing():
        return svc.listing()

    @r.delete("")
    def delete(path: LibraryPath):
        svc.delete(path)
        return {"ok": True}

    @r.get("/cover")
    def cover(path: LibraryPath):
        img = svc.cover(path)
        if not img:
            return Response(status_code=204)
        return FileResponse(img, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})

    return r
