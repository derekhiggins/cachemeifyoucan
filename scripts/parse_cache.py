#!/usr/bin/env python3
"""
Script to parse cache files and pretty print request.body and response.content.
Handles streamed responses by parsing chunks and reconstructing the final content.
"""

import json
import sys
import re
from pathlib import Path
from typing import Dict, Any, List


def parse_streamed_response(content: str) -> str:
    """
    Parse streamed response content and reconstruct the complete chat completion response.

    Args:
        content: Raw streamed response content with "data: " chunks

    Returns:
        Complete chat completion response reconstructed from stream chunks
    """
    lines = content.strip().split('\n')

    # Initialize response structure
    response = {
        "id": None,
        "object": "chat.completion",
        "created": None,
        "model": None,
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": []
            },
            "logprobs": None,
            "finish_reason": None,
            "stop_reason": None
        }],
        "usage": None,
        "prompt_logprobs": None
    }

    tool_calls = {}  # Track tool calls by index
    content_chunks = []

    for line in lines:
        line = line.strip()
        if line.startswith('data: ') and line != 'data: [DONE]':
            try:
                # Extract JSON from data: line
                json_str = line[6:]  # Remove "data: " prefix
                chunk_data = json.loads(json_str)

                # Update response metadata from any chunk
                if 'id' in chunk_data and response['id'] is None:
                    response['id'] = chunk_data['id']
                if 'created' in chunk_data and response['created'] is None:
                    response['created'] = chunk_data['created']
                if 'model' in chunk_data and response['model'] is None:
                    response['model'] = chunk_data['model']
                if 'usage' in chunk_data:
                    response['usage'] = chunk_data['usage']

                # Extract content from chunk
                if 'choices' in chunk_data and chunk_data['choices']:
                    choice = chunk_data['choices'][0]
                    if 'delta' in choice:
                        delta = choice['delta']

                        # Handle regular content
                        if 'content' in delta and delta['content']:
                            content_chunks.append(delta['content'])

                        # Handle tool calls
                        if 'tool_calls' in delta and delta['tool_calls']:
                            for tool_call in delta['tool_calls']:
                                index = tool_call.get('index', 0)

                                # Initialize tool call structure if not exists
                                if index not in tool_calls:
                                    tool_calls[index] = {
                                        'id': None,
                                        'type': None,
                                        'function': {
                                            'name': None,
                                            'arguments': ''
                                        }
                                    }

                                # Update tool call fields
                                if 'id' in tool_call:
                                    tool_calls[index]['id'] = tool_call['id']
                                if 'type' in tool_call:
                                    tool_calls[index]['type'] = tool_call['type']

                                if 'function' in tool_call:
                                    func = tool_call['function']
                                    if 'name' in func:
                                        tool_calls[index]['function']['name'] = func['name']
                                    if 'arguments' in func:
                                        tool_calls[index]['function']['arguments'] += func['arguments']

                    # Get finish_reason and stop_reason from choice
                    if 'finish_reason' in choice and choice['finish_reason']:
                        response['choices'][0]['finish_reason'] = choice['finish_reason']
                    if 'stop_reason' in choice and choice['stop_reason']:
                        response['choices'][0]['stop_reason'] = choice['stop_reason']
                    if 'logprobs' in choice:
                        response['choices'][0]['logprobs'] = choice['logprobs']

            except json.JSONDecodeError:
                # Skip malformed JSON chunks
                continue

    # Set content if we have regular content chunks
    if content_chunks:
        response['choices'][0]['message']['content'] = ''.join(content_chunks)

    # Set tool calls if we have any
    if tool_calls:
        response['choices'][0]['message']['tool_calls'] = [
            tool_calls[index] for index in sorted(tool_calls.keys())
        ]

    # Remove tool_calls if empty, set content to null if we have tool calls
    if not tool_calls:
        del response['choices'][0]['message']['tool_calls']
    else:
        response['choices'][0]['message']['content'] = None

    return json.dumps(response, indent=2, ensure_ascii=False)


def pretty_print_json(data: Any, title: str) -> None:
    """Pretty print JSON data with a title."""
    print(f"\n{'='*60}")
    print(f"{title}")
    print('='*60)

    if isinstance(data, str):
        try:
            # Try to parse as JSON for pretty printing
            parsed = json.loads(data)
            print(json.dumps(parsed, indent=2, ensure_ascii=False))
        except json.JSONDecodeError:
            # If not valid JSON, print as string
            print(data)
    else:
        print(json.dumps(data, indent=2, ensure_ascii=False))


def parse_cache_file(filepath: str) -> None:
    """
    Parse a cache file and pretty print request.body and response.body.

    Args:
        filepath: Path to the cache file to parse
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        print(f"Parsing file: {filepath}")

        # Extract and pretty print request body
        if 'request' in data and 'body' in data['request']:
            pretty_print_json(data['request']['body'], "REQUEST BODY")
        else:
            print("\nNo request.body found in file")

        # Extract and pretty print response body
        if 'response' in data and 'body' in data['response']:
            response_body = data['response']['body']

            # Check if it's streamed format (contains "data: " chunks)
            if isinstance(response_body, str) and 'data: ' in response_body:
                # Parse streamed response
                final_body = parse_streamed_response(response_body)
                if final_body:
                    pretty_print_json(final_body, "RESPONSE BODY (from stream)")
                else:
                    pretty_print_json(response_body, "RESPONSE BODY (raw stream)")
            else:
                # Regular response body
                pretty_print_json(response_body, "RESPONSE BODY")
        else:
            print("\nNo response.body found in file")

    except FileNotFoundError:
        print(f"Error: File '{filepath}' not found")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in file '{filepath}': {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error processing file '{filepath}': {e}")
        sys.exit(1)


def main():
    """Main function to handle command line arguments and process files."""
    if len(sys.argv) < 2:
        print("Usage: python parse_cache.py <cache_file_path> [cache_file_path2] ...")
        print("Example: python parse_cache.py /home/derekh/.cache/cachemeifyoucan/07/070f375ebc6e652cb504d9b15c9f4070.json")
        sys.exit(1)

    # Process each file provided as argument
    for filepath in sys.argv[1:]:
        parse_cache_file(filepath)
        if len(sys.argv) > 2:  # Add separator between multiple files
            print("\n" + "="*80 + "\n")


if __name__ == "__main__":
    main()
