#!/bin/bash
cd "$(dirname "$0")"
rm qkd_engine_config.local.yaml
ln -s $1 qkd_engine_config.local.yaml
