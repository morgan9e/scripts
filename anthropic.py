#!/usr/bin/env python3
import json
import re
import time

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import Response, StreamingResponse, JSONResponse
from starlette.middleware.cors import CORSMiddleware

CLAUDE_BASE_URL = "https://api.anthropic.com/v1/messages"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


def get_api_key(headers: dict) -> str:
    auth = headers.get("authorization")
    if auth:
        parts = auth.split(" ")
        if len(parts) > 1:
            return parts[1]
    return


def format_stream_response_json(claude_response: dict) -> dict:
    typ = claude_response.get("type")
    if typ == "message_start":
        return {
            "id": claude_response["message"]["id"],
            "model": claude_response["message"]["model"],
            "inputTokens": claude_response["message"]["usage"]["input_tokens"],
        }
    elif typ in ("content_block_start", "ping", "content_block_stop", "message_stop"):
        return None
    elif typ == "content_block_delta":
        return {"content": claude_response["delta"]["text"]}
    elif typ == "message_delta":
        return {
            "stopReason": claude_response["delta"].get("stop_reason"),
            "outputTokens": claude_response["usage"]["output_tokens"],
        }
    elif typ == "error":
        return {
            "errorType": claude_response["error"].get("type"),
            "errorMsg": claude_response["error"]["message"],
        }
    else:
        return None


def claude_to_chatgpt_response(claude_response: dict, meta_info: dict, stream: bool = False) -> dict:
    timestamp = int(time.time())
    completion_tokens = meta_info.get("outputTokens", 0) or 0
    prompt_tokens = meta_info.get("inputTokens", 0) or 0

    if meta_info.get("stopReason") and stream:
        return {
            "id": meta_info.get("id"),
            "object": "chat.completion.chunk",
            "created": timestamp,
            "model": meta_info.get("model"),
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "logprobs": None,
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }

    message_content = claude_response.get("content", "")
    result = {
        "id": meta_info.get("id", "unknown"),
        "created": timestamp,
        "model": meta_info.get("model"),
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
        "choices": [{"index": 0}],
    }
    message = {"role": "assistant", "content": message_content}
    if not stream:
        result["object"] = "chat.completion"
        result["choices"][0]["message"] = message
        result["choices"][0]["finish_reason"] = "stop" if meta_info.get("stopReason") == "end_turn" else None
    else:
        result["object"] = "chat.completion.chunk"
        result["choices"][0]["delta"] = message
    return result


async def stream_generator(response: httpx.Response, model: str):
    meta_info = {"model": model}
    buffer = ""
    regex = re.compile(r"event:\s*.*?\s*\ndata:\s*(.*?)(?=\n\n|\s*$)", re.DOTALL)
    async for chunk in response.aiter_text():
        buffer += chunk
        for match in regex.finditer(buffer):
            try:
                decoded_line = json.loads(match.group(1).strip())
            except Exception:
                continue

            formated_chunk = format_stream_response_json(decoded_line)
            if formated_chunk is None:
                continue
            if formated_chunk.get("errorType", None):
                etyp = formated_chunk.get("errorType")
                emsg  = formated_chunk.get("errorMsg")
                data = {"error": {"type": etyp, "code": etyp, "message": emsg, "param": None}}
                yield f"data: {json.dumps(data)}\n\n"
            
            meta_info["id"] = formated_chunk.get("id", meta_info.get("id"))
            meta_info["model"] = formated_chunk.get("model", meta_info.get("model"))
            meta_info["inputTokens"] = formated_chunk.get("inputTokens", meta_info.get("inputTokens"))
            meta_info["outputTokens"] = formated_chunk.get("outputTokens", meta_info.get("outputTokens"))
            meta_info["stopReason"] = formated_chunk.get("stopReason", meta_info.get("stopReason"))
            transformed_line = claude_to_chatgpt_response(formated_chunk, meta_info, stream=True)
            yield f"data: {json.dumps(transformed_line)}\n\n"

        else:
            try:
                resp = json.loads(buffer)
                etyp = resp["error"]["type"]
                emsg = resp["error"]["message"]
                data = {"error": {"type": etyp, "code": etyp, "message": emsg, "param": None}}
                yield f"data: {json.dumps(data)}\n\n"

            except Exception:
                pass

        last_end = 0
        for m in regex.finditer(buffer):
            last_end = m.end()
        buffer = buffer[last_end:]

    yield "data: [DONE]"


@app.get("/v1/models")
async def get_models(request: Request):
    headers = dict(request.headers)
    api_key = get_api_key(headers)
    if not api_key:
        raise HTTPException(status_code=403, detail="Not Allowed")

    async with httpx.AsyncClient() as client:
        anthro_resp = await client.get(
            "https://api.anthropic.com/v1/models",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
        )
    if anthro_resp.status_code != 200:
        raise HTTPException(status_code=anthro_resp.status_code, detail="Error getting models")

    data = anthro_resp.json()
    models_list = [
        {"id": m["id"], "object": m["type"], "owned_by": "Anthropic"}
        for m in data.get("data", [])
    ]

    return JSONResponse(content={"object": "list", "data": models_list})


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    headers = dict(request.headers)
    api_key = get_api_key(headers)
    if not api_key:
        raise HTTPException(status_code=403, detail="Not Allowed")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    
    model = body.get("model")
    messages = body.get("messages", [])
    temperature = body.get("n", 1)
    max_tokens = body.get("max_tokens", 4096)
    stop = body.get("stop")
    stream = body.get("stream", False)
    
    system_message = next((m for m in messages if m.get("role") == "system"), [])
    filtered_messages = [m for m in messages if m.get("role") != "system"]

    claude_request_body = {
        "model": model,
        "messages": filtered_messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stop_sequences": stop,
        "system": system_message.get("content") if system_message else [],
        "stream": stream,
    }
    
    if not stream:
        async with httpx.AsyncClient(timeout=None) as client:
            claude_resp = await client.post(
                CLAUDE_BASE_URL,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
                json=claude_request_body,
            )
        
        if claude_resp.status_code != 200:
            print(claude_resp.content)
            return Response(status_code=claude_resp.status_code, content=claude_resp.content)
        
        resp_json = claude_resp.json()
        
        if resp_json.get("type") == "error":
            result = {
                "error": {
                    "message": resp_json.get("error", {}).get("message"),
                    "type": resp_json.get("error", {}).get("type"),
                    "param": None,
                    "code": resp_json.get("error", {}).get("type"),
                }
            }
        else:
            formated_info = {
                "id": resp_json.get("id"),
                "model": resp_json.get("model"),
                "inputTokens": resp_json.get("usage", {}).get("input_tokens"),
                "outputTokens": resp_json.get("usage", {}).get("output_tokens"),
                "stopReason": resp_json.get("stop_reason"),
            }

            content = ""
            try:
                content = resp_json.get("content", [])[0].get("text", "")
            except Exception:
                pass
            result = claude_to_chatgpt_response({"content": content}, formated_info)
        
        return JSONResponse(
            status_code=claude_resp.status_code,
            content=result
        )
    else:
        async def stream_response(model: str, claude_request_body: dict, api_key: str):
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "POST",
                    CLAUDE_BASE_URL,
                    headers={
                        "Content-Type": "application/json",
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                    },
                    json=claude_request_body,
                ) as response:
                    async for event in stream_generator(response, model):
                        yield event
    
        return StreamingResponse(
            stream_response(model, claude_request_body, api_key),
            media_type = "text/event-stream"
        
        )