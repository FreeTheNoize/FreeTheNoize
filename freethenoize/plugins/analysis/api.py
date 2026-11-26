from fastapi import APIRouter
from pydantic import BaseModel

from ...plugin import LibraryPath


class PathBody(BaseModel):
    path: LibraryPath


class Pair(BaseModel):
    a: LibraryPath
    b: LibraryPath


def routes(svc, ctx) -> APIRouter:
    r = APIRouter()

    @r.post("/analyze")
    def analyze(body: PathBody):
        return svc.analyze(body.path)

    @r.post("/null-test")
    def null_test(body: Pair):
        return svc.null_test(body.a, body.b)

    return r
