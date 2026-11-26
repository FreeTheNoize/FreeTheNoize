import re

from fastapi import APIRouter
from pydantic import BaseModel

_URL = re.compile(r"https?://\S+")


class Text(BaseModel):
    text: str


def routes(svc, ctx) -> APIRouter:
    r = APIRouter()

    @r.post("")
    def add(body: Text):
        """Every link found in the text goes to the queue."""
        urls = list(dict.fromkeys(u.rstrip(").,;]") for u in _URL.findall(body.text or "")))
        if urls:
            svc.add(urls)
        return {"accepted": len(urls)}

    @r.post("/{job_id}/cancel")
    def cancel(job_id: int):
        svc.cancel(job_id)
        return {"ok": True}

    @r.post("/{job_id}/retry")
    def retry(job_id: int):
        svc.retry(job_id)
        return {"ok": True}

    @r.post("/cancel-all")
    def cancel_all():
        svc.cancel_all()
        return {"ok": True}

    @r.post("/clear")
    def clear():
        svc.clear_finished()
        return {"ok": True}

    @r.get("/history")
    def history():
        return svc.history.read()

    return r
