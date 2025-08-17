from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

templates = Jinja2Templates(directory="templates")
router = APIRouter(tags=["tasks-ultra"])

@router.get("/tasks-ultra", response_class=HTMLResponse)
def tasks_ultra_page(request: Request):
    return templates.TemplateResponse("tasks_ultra.html", {"request": request})
