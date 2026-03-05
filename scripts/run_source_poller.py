#!/usr/bin/env python3
"""
Run the job source poller worker.

This worker periodically polls enabled job sources (Telegram channels, websites)
and ingests new job posts into the database.

Usage:
    python scripts/run_source_poller.py
    python scripts/run_source_poller.py --poll-interval 60
    python scripts/run_source_poller.py --max-iterations 10  # For testing
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.source_poller import main

if __name__ == '__main__':
    main()
