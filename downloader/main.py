from fastapi import FastAPI, WebSocket, HTTPException, Request, Depends, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.websockets import WebSocketDisconnect
from typing import Optional
from pydantic import BaseModel
import aiohttp, asyncio
import os, tqdm, json
from collections import defaultdict
from base64 import b64encode

app = FastAPI()

connected_clients = defaultdict(list)
downloads = defaultdict(dict)
completed_downloads = defaultdict(dict)
canceled_downloads = defaultdict(dict)


class DownloadRequest(BaseModel):
    url: str


security = HTTPBasic()


def get_current_username(credentials: HTTPBasicCredentials = Depends(security)):
    return credentials.username


@app.get("/")
async def get(request: Request):
    with open("index.html", "r") as f:
        content = f.read()
    return HTMLResponse(content=content)


@app.get("/file_exists/")
async def file_exists(filename: str):
    if os.path.isfile(filename):
        os.rename(filename, filename + "+")
    return {"exists": os.path.isfile(filename)}


@app.get("/downloads/")
async def get_downloads(username: str = Depends(get_current_username)):
    return {
        "in_progress": list(downloads[username].keys()),
        "completed": list(completed_downloads[username].keys()),
        "canceled": list(canceled_downloads[username].keys()),
    }


@app.post("/download/")
async def download_file(
    request: DownloadRequest, username: str = Depends(get_current_username)
):
    url = request.url
    filename = url.split("/")[-1]

    if url in downloads[username]:
        raise HTTPException(status_code=400, detail="Download already in progress")

    download_task = asyncio.create_task(do_download(url, filename, username))
    downloads[username][url] = download_task

    return {"message": "Download started"}


async def do_download(url, filename, username):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                file_size = int(resp.headers["Content-Length"])
                pbar = tqdm.tqdm(
                    total=(file_size / (1024 * 128)),
                    unit="Mb",
                    ascii=True,
                    unit_scale=True,
                )
                with open(filename, "wb") as f:
                    chunk_size = 1024
                    downloaded_size = 0
                    last_progress = 0
                    async for chunk in resp.content.iter_any():
                        pbar.update(len(chunk) / (1024 * 128))
                        if url not in downloads[username]:
                            pbar.close()
                            return
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        # Notify the client about the progress
                        progress = int((downloaded_size / file_size) * 100)
                        # Check if the integer percentage has changed
                        if progress != last_progress:
                            last_progress = progress
                            await notify_clients(progress, url, username)
                pbar.close()
    finally:
        if url in downloads[username]:
            if url not in canceled_downloads[username]:
                completed_downloads[username][url] = downloads[username][url]
            del downloads[username][url]


@app.post("/cancel/")
async def cancel_download(
    request: DownloadRequest, username: str = Depends(get_current_username)
):
    url = request.url
    if url in downloads[username]:
        canceled_downloads[username][url] = downloads[username][url]
        downloads[username][url].cancel()
        return {"message": "Download canceled"}
    if url in completed_downloads[username]:
        del completed_downloads[username][url]
        return {"message": "Download removed"}
    else:
        raise HTTPException(status_code=404, detail="No such download")


@app.websocket("/ws/{username}")
async def websocket_endpoint(websocket: WebSocket, username: str):
    await websocket.accept()
    connected_clients[username].append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        connected_clients[username].remove(websocket)


async def notify_clients(progress, url, username):
    for client in connected_clients[username]:
        await client.send_text(json.dumps({"progress": progress, "url": url}))