#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    echo "Usage: $0 [dev|test]"
    echo "  dev   Start services for local development"
    echo "  test  Build and run the full test suite inside containers"
    exit 1
}

if [ $# -ne 1 ]; then
    usage
fi

case "$1" in
    dev)
        docker compose -f "${SCRIPT_DIR}/docker-compose.yml" up
        ;;
    test)
        docker compose -f "${SCRIPT_DIR}/docker-compose.test.yml" up \
            --build \
            --exit-code-from test \
            --abort-on-container-exit
        ;;
    *)
        usage
        ;;
esac
