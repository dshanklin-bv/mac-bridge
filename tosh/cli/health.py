"""
tosh health - Check daemon health status.

Usage:
    python -m tosh.cli.health
    python -m tosh.cli.health --json
"""

import argparse
import json
import sys

from tosh.utils.health import get_health_status, print_health_status


def main():
    parser = argparse.ArgumentParser(description='Check tosh daemon health')
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output JSON format'
    )

    args = parser.parse_args()

    status = get_health_status()

    if args.json:
        print(json.dumps(status, indent=2))
    else:
        print_health_status()

    # Exit code: 0 if healthy, 1 if degraded
    sys.exit(0 if status["healthy"] else 1)


if __name__ == '__main__':
    main()
