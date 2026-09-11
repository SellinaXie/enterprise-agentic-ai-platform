#!/bin/sh
set -eu

test_database="${POSTGRES_TEST_DB:-enterprise_ai_test}"
case "$test_database" in
  *test*) ;;
  *)
    echo "POSTGRES_TEST_DB must contain 'test'" >&2
    exit 1
    ;;
esac

case "$test_database" in
  *[!a-zA-Z0-9_]*)
    echo "POSTGRES_TEST_DB may contain only letters, numbers, and underscores" >&2
    exit 1
    ;;
esac

if [ "$test_database" = "$POSTGRES_DB" ]; then
  echo "POSTGRES_TEST_DB must differ from POSTGRES_DB" >&2
  exit 1
fi

createdb --username "$POSTGRES_USER" "$test_database"
