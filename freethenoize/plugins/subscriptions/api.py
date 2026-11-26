from fastapi import APIRouter, Body
from pydantic import BaseModel


class SubBody(BaseModel):
    url: str
    interval_hours: float = 6


def routes(svc, ctx) -> APIRouter:
    r = APIRouter()

    @r.get("")
    def list_():
        return svc.list()

    @r.post("")
    def add(body: SubBody):
        return svc.add(body.url, body.interval_hours)

    @r.patch("/{sub_id}")
    def update(sub_id: str, patch: dict = Body(...)):
        return svc.update(sub_id, patch)

    @r.delete("/{sub_id}")
    def delete(sub_id: str):
        svc.remove(sub_id)
        return {"ok": True}

    @r.post("/{sub_id}/check")
    def check(sub_id: str):
        svc.check(sub_id)
        return {"ok": True}

    return r
