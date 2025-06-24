#!/usr/bin/env python3
"""
Script to convert cached request JSON files to curl commands.
Reads JSON files from ~/.cache/cachemeifyoucan/ and outputs curl commands to replay HTTP requests.
"""

import json
import argparse
import sys
import os
import glob
import subprocess
from pathlib import Path
import shlex


def escape_for_curl(value, double_quotes=False):
    """Escape a string value for safe use in curl command."""
    if isinstance(value, str):
        if double_quotes:
            return f'"{value}"'
        else:
            return shlex.quote(value)
    return str(value)


def json_to_curl(json_data, base_url="https://api.openai.com"):
    """
    Convert a JSON request object to a curl command.

    Args:
        json_data: Dictionary containing the parsed JSON data
        base_url: Base URL to prepend to the path

    Returns:
        String containing the curl command
    """
    request = json_data.get('request', {})

    method = request.get('method', 'GET')
    base_url = request.get('target_url', base_url)
    path = request.get('path', '/')
    headers = request.get('headers', {})
    body = request.get('body', '')

    # Start building the curl command
    curl_parts = ['curl', '-s']

    # Add method
    if method != 'GET':
        curl_parts.extend(['-X', method])

    # Add headers, excluding some that curl handles automatically or are sensitive
    skip_headers = {
        'content-length',
        'host',
        'accept-encoding',  # Let curl handle this
        'connection',       # Let curl handle this
    }

    for header_name, header_value in headers.items():
        header_name_lower = header_name.lower()
        if header_name_lower not in skip_headers:
            # Handle authorization header specially to mask it
            if header_name_lower == 'authorization' and header_value == '***':
                header_value = 'Bearer $OPENAI_API_KEY'
                # Put this at the start so its easier to find in a long commandline
                curl_parts.insert(1, escape_for_curl(f'{header_name}: {header_value}', double_quotes=True))
                curl_parts.insert(1, '-H')
            else:
                # Wrap entire header string in quotes
                curl_parts.extend(['-H', escape_for_curl(f'{header_name}: {header_value}', double_quotes=True)])

    # Add body data if present, wrapped in quotes
    if body:
        curl_parts.extend(['-d', escape_for_curl(body)])

    # Add URL
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    curl_parts.append(escape_for_curl(url))

    return ' '.join(curl_parts)


def process_json_file(file_path):
    """Process a single JSON file and return the curl command."""
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)

        curl_command = json_to_curl(data)
        return curl_command

    except Exception as e:
        print(f"Error processing {file_path}: {e}", file=sys.stderr)
        return None


def find_json_files(cache_dir):
    """Find all JSON files in the cache directory."""
    cache_path = Path(cache_dir)
    if not cache_path.exists():
        print(f"Cache directory {cache_dir} does not exist", file=sys.stderr)
        return []

    # Find all .json files in subdirectories
    json_files = []
    for subdir in cache_path.iterdir():
        if subdir.is_dir():
            json_files.extend(subdir.glob('*.json'))

    return json_files


def run_curl_command(curl_command, timeout=30):
    """
    Execute a curl command and return the results.

    Args:
        curl_command: The curl command string to execute
        timeout: Timeout in seconds for the command

    Returns:
        Dictionary with 'returncode', 'stdout', 'stderr', 'command'
    """
    try:
        # Replace environment variables in the command
        expanded_command = curl_command

        # Handle OPENAI_API_KEY specifically
        if '$OPENAI_API_KEY' in curl_command:
            api_key = os.getenv('OPENAI_API_KEY')
            if api_key:
                expanded_command = curl_command.replace('$OPENAI_API_KEY', api_key)
            else:
                return {
                    'returncode': -1,
                    'stdout': '',
                    'stderr': 'OPENAI_API_KEY environment variable not set',
                    'command': curl_command
                }

        # Use shlex.split to properly handle quoted arguments
        cmd_parts = shlex.split(expanded_command)

        # Run the command
        result = subprocess.run(
            cmd_parts,
            capture_output=True,
            text=True,
            timeout=timeout
        )

        return {
            'returncode': result.returncode,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'command': curl_command
        }

    except subprocess.TimeoutExpired:
        return {
            'returncode': -1,
            'stdout': '',
            'stderr': f'Command timed out after {timeout} seconds',
            'command': curl_command
        }
    except Exception as e:
        return {
            'returncode': -1,
            'stdout': '',
            'stderr': f'Error executing command: {str(e)}',
            'command': curl_command
        }


def main():
    parser = argparse.ArgumentParser(
        description='Convert cached request JSON files to curl commands'
    )
    parser.add_argument(
        'files',
        nargs='*',
        help='JSON files to process (if not specified, processes all files in cache)'
    )
    parser.add_argument(
        '--cache-dir',
        default=os.path.expanduser('~/.cache/cachemeifyoucan'),
        help='Cache directory path (default: ~/.cache/cachemeifyoucan)'
    )
    parser.add_argument(
        '--output-file',
        help='Output file to write curl commands (default: stdout)'
    )
    parser.add_argument(
        '--run',
        action='store_true',
        help='Execute the curl commands instead of just printing them'
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=30,
        help='Timeout in seconds for curl commands when using --run (default: 30)'
    )

    args = parser.parse_args()

    # Determine which files to process
    if args.files:
        json_files = [Path(f) for f in args.files]
    else:
        json_files = find_json_files(args.cache_dir)

    if not json_files:
        print("No JSON files found to process", file=sys.stderr)
        return 1

    # Open output file or use stdout
    if args.output_file:
        output = open(args.output_file, 'w')
    else:
        output = sys.stdout

    try:
        for json_file in json_files:
            curl_command = process_json_file(json_file)
            if curl_command:
                output.write(f"# From: {json_file}\n")

                if args.run:
                    # Execute the curl command
                    output.write(f"# Command: {curl_command}\n")
                    result = run_curl_command(curl_command, args.timeout)

                    output.write(f"# Return code: {result['returncode']}\n")
                    if result['stdout']:
                        output.write(f"# Response:\n{result['stdout']}\n")
                    if result['stderr']:
                        output.write(f"# Error output:\n{result['stderr']}\n")
                    output.write("\n")
                else:
                    # Just output the curl command
                    output.write(f"{curl_command}\n\n")

    finally:
        if args.output_file:
            output.close()

    return 0


if __name__ == '__main__':
    sys.exit(main())
