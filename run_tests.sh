#!/bin/bash
set -e
# Test runner for UUID stability edge cases

echo "🧪 Running UUID Stability Edge Case Tests"
echo "=========================================="

# Make test scripts executable
chmod +x run_edge_case_tests.py
chmod +x test_uuid_stability.py

# Run the main edge case tests
echo "🚀 Starting comprehensive edge case validation..."
python3 run_edge_case_tests.py

exit_code=$?

echo ""
echo "📋 Test Summary:"
if [ $exit_code -eq 0 ]; then
    echo "✅ All tests passed - UUID stability fix is working!"
else
    echo "❌ Some tests failed - check output above for details"
fi

exit $exit_code