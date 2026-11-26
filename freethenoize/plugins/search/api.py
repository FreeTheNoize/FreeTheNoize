from fastapi import APIRouter


def routes(svc, ctx) -> APIRouter:
    r = APIRouter()

    @r.get("")
    def search(q: str = ""):
        return svc.search(q)

    return r
