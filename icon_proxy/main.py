from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

app = FastAPI()

app.mount("/icons", StaticFiles(directory="icons"), name="icons")

reds = {"live-calendar": "https://outlook.live.com/calendar/0/view/month", 
        "twitter": "https://twitter.com"}

@app.get("/{icon_name}")
async def redirect_html(icon_name: str):
    redirect_url = reds.get(icon_name)
    html_content = f"""<html>
        <head>
            <meta http-equiv="refresh" content="0;url={redirect_url}" />
              <link rel="icon" type="image/x-icon" href="/favicon.ico">
        </head>
        <body>
            Redirecting...
        </body>
        </html>"""
    return HTMLResponse(content=html_content)

@app.get("/{icon_name}/favicon.ico")
async def get_icon(icon_name: str):
    icon_path = Path(f"icons/{icon_name}.ico")
    if icon_path.exists():
        return FileResponse(icon_path)
    else:
        return {"error": "Icon not found"}
