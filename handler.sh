#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "Usage: $0 [dev|test]"
    echo "  dev   Start postgres and mongo for local development"
    echo "  test  Build and run the full test suite inside containers"
    exit 1
}

if [ $# -ne 1 ]; then
    usage
fi

case "$1" in
    dev)
        docker compose up
        ;;
    test)
        docker compose -f docker-compose.test.yml up \
            --build \
            --exit-code-from test \
            --abort-on-container-exit
        ;;
    *)
        usage
        ;;
esac
