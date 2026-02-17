#!/bin/bash
# Run backend test suite (enterprise, simple).
# Usage: from repo root: cd backtuki && ./run_tests.sh
# Or: ./backtuki/run_tests.sh
set -e
cd "$(dirname "$0")"
echo "Running backend tests..."
python manage.py test apps.whatsapp.tests apps.accommodations.tests apps.events.tests payment_processor.tests --verbosity=2
echo "Tests finished."
