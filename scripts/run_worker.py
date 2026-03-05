#!/usr/bin/env python3
"""
CLI script to run the notification queue worker.

Usage:
    python scripts/run_worker.py
    python scripts/run_worker.py --poll-interval 10 --batch-size 5
    python scripts/run_worker.py --max-iterations 100  # Run 100 iterations then stop
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.worker import main

if __name__ == '__main__':
    main()
