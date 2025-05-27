"""
cachemeifyoucan: A FastAPI-based HTTP cache/proxy server.
"""
from fastapi import FastAPI, Request, Response
import uvicorn
import httpx
import hashlib
import json
import os
import yaml
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# store to $HOME/.cache/cachemeifyoucan
cache_dir = os.path.expanduser("~/.cache/cachemeifyoucan")
# Calculate a cache key from passed in data
async def calculate_cache_path(method, url, headers, body):
    # Create a normalized representation of the request
    normalized = {
        "method": method,
        "url": url,
        "body": body.decode("utf-8", errors="replace") if body else "",
    }

    # Filter out headers that affect caching
    cache_headers = {}
    for key, value in headers.items():
        if key not in ["x-stainless-retry-count"]:
            cache_headers[key] = value.strip()

    normalized["headers"] = cache_headers

    # Create a JSON string and hash it
    json_str = json.dumps(normalized, sort_keys=True)
    hash_obj = hashlib.md5(json_str.encode("utf-8"))
    key = hash_obj.hexdigest()
    # shard by first 2 characters of the key    
    shard = key[:2]
    return os.path.join(cache_dir, shard, key+".json")

async def get_response_from_cache(cache_path: str) -> dict | None:
    if os.path.exists(cache_path):
        logger.info(f"Getting response from cache: {cache_path}")
        with open(cache_path, "r") as f:
            return json.load(f)["response"]
    return None

async def save_response_to_cache(request_data, cache_path, response_data):
    # Mask authorization header
    headers = request_data["headers"]
    if "authorization" in headers:
        headers["authorization"] = "***"

    cache_data = {
        "request": request_data,
        "response": response_data,
    }
    logger.info(f"Saving response to cache: {cache_path}")
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(cache_data, f)

app = FastAPI()
app.state.config = None

@app.on_event("startup")
async def startup_event():
    config_path = os.environ.get("CACHE_CONFIG", "cachemeifyoucan.yaml")
    logging.info(f"Loading config from {config_path}, cache_dir: {cache_dir}")
    with open(config_path, 'r') as f:
        app.state.config = yaml.safe_load(f)

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def catch_all(request: Request, path: str = ""):
    method = str(request.method)
    headers = dict(request.headers)
    body = await request.body()

    # Extract target name and new path
    if not path or "/" not in path:
        return Response(content="Invalid path", status_code=400)
    target_name, *rest = path.split("/", 1)
    new_path = rest[0] if rest else ""

    config = app.state.config
    if not config or target_name not in config.get("targets", {}):
        return Response(content=f"Unknown target: {target_name}", status_code=404)
    target_url = config["targets"][target_name]["url"]

    request_data = {
        "method": method,
        "path": new_path,
        "headers": headers,
        "body": body.decode("utf-8", errors="replace") if body else "",
    }

    cache_path = await calculate_cache_path(method, path, headers, body)

    # get a response from the cache if it exists
    response = await get_response_from_cache(cache_path)
    if response:
        # remove headers that fastapi adds
        for header in ["transfer-encoding", "content-length", "content-encoding", "connection"]:
            response["headers"].pop(header, None)
        return Response(content=response["content"].encode("utf-8"), status_code=response["status_code"], headers=response["headers"])
    
    # Forward the request to the selected target
    response_data = await forward_request(request_data, target_url)
    await save_response_to_cache(request_data, cache_path, response_data)

    # remove headers that fastapi adds
    for header in ["transfer-encoding", "content-length", "content-encoding", "connection"]:
        response_data["headers"].pop(header, None)
    return Response(content=response_data["content"], status_code=response_data["status_code"], headers=response_data["headers"])

async def forward_request(request_data, target_url):
    method = request_data["method"]
    path = request_data["path"]
    headers = request_data["headers"]
    body = request_data["body"]

    headers.pop("host", None)
    url = f"{target_url}/{path}" if path else target_url
    async with httpx.AsyncClient() as client:
        response = await client.request(
            method=method,
            url=url,
            headers=headers,
            content=body,
            follow_redirects=True,
            timeout=90,
        )
        response_data = {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "content": response.content.decode("utf-8", errors="replace") if response.content else "",
        }
        return response_data

def main():
    uvicorn.run("cachemeifyoucan:app", host="0.0.0.0", port=9999, reload=False)

if __name__ == "__main__":
    main()
