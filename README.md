# cachemeifyoucan

A FastAPI-based HTTP cache/proxy server.

**cachemeifyoucan** is designed to assist development and testing against expensive or rate-limited APIs. By caching API responses, it allows you to run unit tests or repeat development work multiple times without repeatedly hitting the upstream API, saving both time and cost.

## Installation

You can install directly from GitHub:

```bash
pip install git+https://github.com/derekhiggins/cachemeifyoucan.git
```

## Usage

Run the server:

```bash
uvicorn cachemeifyoucan:app --host 0.0.0.0 --port 9999
```

## Configuration

Edit `cachemeifyoucan.yaml` to add your target URLs. 

Each top-level key in the YAML file is a target name (e.g., `openai`). Under each target, specify the `url` field with the base URL you want requests to be proxied to. You can add multiple targets by adding more entries at the top level. For example:

```yaml
openai:
  url: https://api.openai.com
myapi:
  url: https://my.custom.api/v1
```

You can then access these targets by making requests to `/openai/...` or `/myapi/...` on your cachemeifyoucan server.

## Testing the Cache

You can test the caching behavior using `curl` to make POST requests to your running cache server. The first request will be slow (cache miss), the second identical request will be fast (cache hit), and changing the request body will result in another cache miss.

### 1. First Request (Cache Miss)
This request will be slow because the response is not yet cached:

```bash
# First request: expect a slow response (cache miss)
time curl -sq http://localhost:9999/openai/v1/chat/completions \
  -H 'authorization: Bearer YOURTOKENHERE' \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role":"user", "content":"List 2 great reasons to visit Sligo, be brief"}],
    "max_tokens": 4096,
    "temperature": 0.6
  }' | jq .choices[0].message.content
```

### 2. Second Request (Cache Hit)
Repeat the exact same request. This time, the response should be almost instantaneous because it is served from the cache:

```bash
# Second request: expect a fast response (cache hit)
time curl -sq http://localhost:9999/openai/v1/chat/completions \
  -H 'authorization: Bearer YOURTOKENHERE' \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role":"user", "content":"List 2 great reasons to visit Sligo, be brief"}],
    "max_tokens": 4096,
    "temperature": 0.6
  }' | jq .choices[0].message.content
```

### 3. Change the Request (Cache Miss Again)
If you change any part of the POST body (for example, the `temperature`), the cache will miss and the request will be slow again:

```bash
# Third request: change temperature, expect a slow response (cache miss)
time curl -sq http://localhost:9999/openai/v1/chat/completions \
  -H 'authorization: Bearer YOURTOKENHERE' \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role":"user", "content":"List 2 great reasons to visit Sligo, be brief"}],
    "max_tokens": 4096,
    "temperature": 0.55
  }' | jq .choices[0].message.content
```

You should see the first and third requests take noticeably longer than the second, demonstrating the effect of caching.

### Viewing Newly Created Cache Entries

After making requests, you can view the newly created cache entries (which are stored as JSON files) using the following command:

```bash
find ~/.cache/cachemeifyoucan/ -type f -mmin -1
```

This will list all cache files modified in the last minute. Each file corresponds to a unique request/response pair.

---

## Editing Cache Entries (Custom Responses)

You can manually edit a cache entry to provide a custom response for a given request. This is useful for testing how your application handles specific API responses, or for simulating error conditions and edge cases.

1. **Locate the cache file**: Use the `find` command above to identify the relevant cache file for the request you want to modify.
2. **Open the cache file**: The cache files are standard JSON. Open the file in your favorite text editor, for example:
   ```bash
   vi ~/.cache/cachemeifyoucan/2b/2bf3d545329bd5dd5cf5aaa5537c3159.json
   ```
3. **Edit the response**: Modify the JSON content to reflect the custom response you want to serve. Save the file.
4. **Test**: The next time you make the same request, the server will return your custom response from the cache.

> **Note:** Be careful to maintain valid JSON structure when editing cache files manually.


# Security Note on Cached Data

Cache files store request and response data, including headers and body content. To mitigate risks, the Authorization header in the stored request data within the cache file is masked (replaced with "***"). However, the response content is stored as received from the upstream server. In future we may make the list of masked Headers configurable.
