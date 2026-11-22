#!/bin/bash
curl -s http://127.0.0.1:8771/api/jobs -o /tmp/jobs.json
python3 /tmp/jobsread.py
