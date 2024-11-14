#!/usr/bin/env python3
# Convert JSON to YAML
#
# Usage:
#     $ python3 json2yaml.py config.json

import json
import sys
from pathlib import Path
from queue import SimpleQueue

import yaml

if len(sys.argv) < 2:
    print("json2yaml.py <FILE_OR_DIR> ...", file=sys.stderr)
    sys.exit(1)

def json2yaml(text):
    text = json.loads(text)
    return yaml.dump(text, sort_keys=False)

def yaml2json(text):
    text = yaml.load(text)
    return json.dumps(text)

# Populate tokens
tokens = SimpleQueue()
for token in sys.argv[1:]:
    tokens.put(token)

# Process tokens
while not tokens.empty():
    path = Path(tokens.get())
    if not path.exists():
        print(f"'{path}' does not exist", file=sys.stderr)
        continue

    # Add all JSON ext files in shallow directory
    if path.is_dir():
        for token in path.glob("*.json"):
            tokens.put(token)
        continue
    
    # Perform conversion
    with open(path) as f:
        text = f.read()
    text = json2yaml(text)

    # Write to YAML ext
    # - config.default.json -> config.default.yaml
    # - config.default      -> config.default.yaml
    suffix = ".yaml"
    if path.suffix != ".json":
        suffix = path.suffix + suffix
    target = path.with_suffix(suffix)
    with open(target, "w") as f:
        f.write(text)
