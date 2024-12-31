#!/usr/bin/env python

import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse, FileResponse
import requests
import datetime

app = FastAPI()
hosts = [
    "SERVER1",
    "SERVER2",
    "SERVER3",
    "SERVER4"
    ]
cache = {}

def find_fit(parent):
    print(cache)
    hosts_local = hosts.copy()
    if parent in cache.keys():
        print(f"DEBUG: Cache Hit {parent}: {cache[parent]}")
        idx = hosts.index(cache[parent])
        if idx:
            hosts_local[idx], hosts_local[0] = hosts_local[0], hosts_local[idx]

    for host in hosts_local:
        try:
            print(f"DEBUG: Tesing for http://{host}/{parent}")
            if requests.head(f"http://{host}/{parent}", allow_redirects=True).status_code == 200:
                cache[parent] = host
                return host
            else:
                cache[parent] = ""
        except Exception:
            pass
    return None

def log(level, status_code, path, header):
    print(f'{level}: [{datetime.datetime.now()}] "{status_code} {path} "{header.get("User-Agent")}"')

@app.get("/{path:path}")
async def index(request: Request, path: str):
    if path in [None, "", "favicon.ico", "index.html"]:
        if path in [None, ""]:
            path = "index.html"
        print(f'RETURN: [{datetime.datetime.now()}] "200 {path} "{request.headers.get("User-Agent")}"')
        return FileResponse(path)
    
    server = find_fit(path.split("/")[0])
    
    if server:
        print(f'RETURN: [{datetime.datetime.now()}] "301 http://{server}/{path}" "{request.headers.get("User-Agent")}"')
        return RedirectResponse(url=f"http://{server}/{path}")
    else:
        print(f'RETURN: [{datetime.datetime.now()}] "404 Not found" "{request.headers.get("User-Agent")}"')
        raise HTTPException(status_code=404, detail="No available server.")

if __name__=="__main__":
    print('Starting Server...')
    uvicorn.run(
        "fallback:app",
        host="0.0.0.0",
        port=8080,
        log_level="info",
        reload=True,
    )

