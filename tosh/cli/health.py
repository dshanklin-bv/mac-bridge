"""
tosh health - Check daemon health status.

Usage:
    python -m tosh.cli.health              # Show local health status
    python -m tosh.cli.health --json       # Output JSON format
    python -m tosh.cli.health --report     # Run checks and report to argus
"""

import argparse
import json
import sys

from tosh.utils.health import (
    get_health_status, print_health_status,
    run_health_checks, report_health_to_argus
)


def main():
    parser = argparse.ArgumentParser(description='Check tosh daemon health')
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output JSON format'
    )
    parser.add_argument(
        '--report',
        action='store_true',
        help='Run health checks and report to argus.agent_health'
    )
    parser.add_argument(
        '--files-transferred',
        type=int,
        default=0,
        help='Number of files transferred (for photo sync reporting)'
    )

    args = parser.parse_args()

    if args.report:
        # Run health checks and report to argus
        result = run_health_checks()

        # Report to argus
        report_health_to_argus(
            status=result["status"],
            sync_type="daemon_cycle",
            rows_synced=result["rows_synced"],
            files_transferred=args.files_transferred,
            errors=result["errors"],
            checks_passed=result["checks_passed"]
        )

        print(f"Health: {result['status'].upper()}")
        print(f"Checks: {result['checks_passed']}")
        if result["errors"]:
            print(f"Errors: {result['errors']}")
        print("Reported to argus.agent_health")

        sys.exit(0 if result["status"] == "healthy" else 1)

    # Default: show local health status
    status = get_health_status()

    if args.json:
        print(json.dumps(status, indent=2))
    else:
        print_health_status()

    # Exit code: 0 if healthy, 1 if degraded
    sys.exit(0 if status["healthy"] else 1)


if __name__ == '__main__':
    main()
