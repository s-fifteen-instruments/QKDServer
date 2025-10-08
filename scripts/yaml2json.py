#!/usr/bin/env python3
"""Converts YAML formatted files into readable JSON.

This script can also convert from JSON to YAML, despite its name for its
primary YAML-to-JSON usage.

Examples:
    $ python3 json2yaml.py config.json
"""

import json
import sys
from pathlib import Path
from queue import SimpleQueue

import yaml


def swap_suffix(path, default_format="json"):
    """Returns path with swapped JSON/YAML suffix.

    Examples:
        >>> def f(filepath):
        ...     path = Path(filepath)
        ...     return str(swap_suffix(path))

        >>> f("config.default.yaml")
        'config.default.json'
        >>> f("config.default.json")
        'config.default.yaml'
        >>> f("config.default")
        'config.default.json'
    """
    suffix = {".json": ".yaml", ".yaml": ".json"}.get(
        path.suffix, f"{path.suffix}.{default_format}"
    )
    return path.with_suffix(suffix)


def json2yaml(text):
    text = json.loads(text)
    return yaml.safe_dump(text, default_flow_style=False, sort_keys=False)


def yaml2json(text):
    # Note: result terminates with expected '}', not '\n'
    text = yaml.safe_load(text)
    return json.dumps(text, allow_nan=False, indent=2, sort_keys=False)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("json2yaml.py <FILE_OR_DIR> ...", file=sys.stderr)
        sys.exit(1)

    # Paths are queued to allow for simple requeuing of directory files
    q = SimpleQueue()
    for token in sys.argv[1:]:
        q.put(token)

    # Process paths
    while not q.empty():
        path = Path(q.get())
        if not path.exists():
            print(f"'{path}' does not exist", file=sys.stderr)
            continue

        # Add all YAML files in shallow directory
        if path.is_dir():
            for token in path.glob("*.yaml"):
                q.put(token)
            continue

        # Perform conversion
        with open(path) as f:
            text = f.read()
        convert = {
            ".yaml": yaml2json,
            ".json": json2yaml,
        }.get(path.suffix, yaml2json)
        text = convert(text)

        target = swap_suffix(path)
        with open(target, "w") as f:
            f.write(text)
