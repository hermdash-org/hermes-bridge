#!/usr/bin/env python3
"""
Higgsfield CLI Wrapper — Drop-in replacement for the Higgsfield CLI.

This script mimics the Higgsfield CLI interface but uses the Python SDK internally.
Skills can call this instead of the actual CLI binary.

Usage (from skills):
    python3 -m bridge.HiggsfieldAPI.cli_wrapper generate create nano_banana_2 \
        --prompt "sunset over mountains" \
        --aspect_ratio 16:9 \
        --wait
"""

import sys
import json
import argparse
from typing import Dict, Any


def parse_generate_args(args):
    """Parse 'generate create' command arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument('model', help='Model name')
    parser.add_argument('--prompt', required=True, help='Generation prompt')
    parser.add_argument('--aspect_ratio', '--aspect-ratio', help='Aspect ratio (e.g., 16:9)')
    parser.add_argument('--resolution', help='Resolution (e.g., 2k, 1080p)')
    parser.add_argument('--image', help='Input image URL or path')
    parser.add_argument('--video', help='Input video URL or path')
    parser.add_argument('--duration', type=int, help='Video duration in seconds')
    parser.add_argument('--quality', help='Quality setting')
    parser.add_argument('--mode', help='Mode setting')
    parser.add_argument('--wait', action='store_true', help='Wait for completion')
    parser.add_argument('--json', action='store_true', help='Output JSON')
    
    # Parse known args (ignore unknown for flexibility)
    parsed, unknown = parser.parse_known_args(args)
    
    # Build arguments dict
    kwargs = {}
    if parsed.aspect_ratio:
        kwargs['aspect_ratio'] = parsed.aspect_ratio
    if parsed.resolution:
        kwargs['resolution'] = parsed.resolution
    if parsed.image:
        kwargs['image'] = parsed.image
    if parsed.video:
        kwargs['video'] = parsed.video
    if parsed.duration:
        kwargs['duration'] = parsed.duration
    if parsed.quality:
        kwargs['quality'] = parsed.quality
    if parsed.mode:
        kwargs['mode'] = parsed.mode
    
    return parsed.model, parsed.prompt, kwargs, parsed.wait, parsed.json


def generate_create(args):
    """Handle 'generate create' command."""
    try:
        from .client import HiggsfieldAPI
        
        model, prompt, kwargs, wait, output_json = parse_generate_args(args)
        
        api = HiggsfieldAPI()
        
        if wait:
            # Wait for completion
            result = api.generate(model=model, prompt=prompt, **kwargs)
            
            if output_json:
                print(json.dumps(result, indent=2))
            else:
                # Print result URL (mimics CLI output)
                if 'images' in result and result['images']:
                    print(result['images'][0]['url'])
                elif 'videos' in result and result['videos']:
                    print(result['videos'][0]['url'])
                else:
                    print(json.dumps(result, indent=2))
        else:
            # Submit without waiting
            controller = api.submit(model=model, prompt=prompt, **kwargs)
            request_id = getattr(controller, 'request_id', 'unknown')
            
            if output_json:
                print(json.dumps({"request_id": request_id, "status": "submitted"}))
            else:
                print(f"Request submitted: {request_id}")
        
        return 0
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def upload_file(args):
    """Handle 'upload' command."""
    try:
        from .client import HiggsfieldAPI
        
        parser = argparse.ArgumentParser()
        parser.add_argument('file_path', help='File to upload')
        parser.add_argument('--json', action='store_true', help='Output JSON')
        parsed = parser.parse_args(args)
        
        api = HiggsfieldAPI()
        url = api.upload_file(parsed.file_path)
        
        if parsed.json:
            print(json.dumps({"url": url}))
        else:
            print(url)
        
        return 0
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: higgsfield <command> [args]", file=sys.stderr)
        print("Commands: generate, upload", file=sys.stderr)
        return 1
    
    command = sys.argv[1]
    
    if command == 'generate':
        if len(sys.argv) < 3 or sys.argv[2] != 'create':
            print("Usage: higgsfield generate create <model> --prompt <prompt> [options]", file=sys.stderr)
            return 1
        return generate_create(sys.argv[3:])
    
    elif command == 'upload':
        return upload_file(sys.argv[2:])
    
    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        print("Supported commands: generate, upload", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
