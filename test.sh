#!/bin/bash
# Unified test runner for the entire project

echo "🧪 Running all project tests..."
echo

# Run your new unit tests
echo "📦 Running lagasafn unit tests:"
PYTHONPATH=. ./venv/bin/pytest lagasafn/law/tests/ -v
UNIT_EXIT=$?

echo
echo "🌐 Running Django tests:"
cd codex-api
../venv/bin/python manage.py test --verbosity=2
DJANGO_EXIT=$?
cd ..

echo
echo "📊 Test Summary:"
if [ $UNIT_EXIT -eq 0 ]; then
    echo "  Unit tests:   ✅ PASSED"
else
    echo "  Unit tests:   ❌ FAILED"
fi

if [ $DJANGO_EXIT -eq 0 ]; then
    echo "  Django tests: ✅ PASSED"
else
    echo "  Django tests: ❌ FAILED"
fi

if [ $UNIT_EXIT -eq 0 ] && [ $DJANGO_EXIT -eq 0 ]; then
    echo
    echo "🎉 All tests passed!"
    exit 0
else
    echo
    echo "💥 Some tests failed!"
    exit 1
fi