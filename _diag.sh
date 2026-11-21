#!/bin/bash
set -e
/opt/viewdl/.venv/bin/python /tmp/variants.py
ls -la /tmp/var_*.bin | awk '{print $9, $5}'
for f in /tmp/var_*.bin; do file "$f" | cut -c1-90; done
