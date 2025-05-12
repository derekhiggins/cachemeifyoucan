# cachemeifyoucan

A FastAPI-based HTTP cache/proxy server.

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
