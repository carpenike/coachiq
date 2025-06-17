#!/bin/bash
# Command: /check-service-patterns
# Description: Check for legacy service access patterns that should be migrated

set -euo pipefail

echo "🔍 Checking for legacy service access patterns..."
echo ""

# Check for old dependencies imports
echo "1️⃣ Checking for legacy backend.core.dependencies imports..."
if rg -l "from backend\.core\.dependencies import" backend/ --type py 2>/dev/null | grep -v dependencies_v2.py; then
    echo "❌ Found files using old dependencies module (should use dependencies_v2)"
    echo ""
else
    echo "✅ No legacy dependencies imports found"
    echo ""
fi

# Check for get_*_from_request patterns
echo "2️⃣ Checking for get_*_from_request() patterns..."
if rg "get_\w+_from_request" backend/ --type py 2>/dev/null | grep -v "# Legacy"; then
    echo "❌ Found get_*_from_request() usage (should use get_*() from dependencies_v2)"
    echo ""
else
    echo "✅ No get_*_from_request() patterns found"
    echo ""
fi

# Check for direct app.state access
echo "3️⃣ Checking for direct app.state access..."
if rg "app\.state\.\w+" backend/ --type py 2>/dev/null | grep -v -E "(service_registry|# Legacy|test_)"; then
    echo "⚠️  Found direct app.state access (should use dependency injection)"
    echo ""
else
    echo "✅ No problematic app.state access found"
    echo ""
fi

# Check for global service variables
echo "4️⃣ Checking for global service variables..."
if rg "^[a-z_]+_service\s*=\s*None" backend/ --type py 2>/dev/null | grep -v "test_"; then
    echo "⚠️  Found global service variables (should use ServiceRegistry)"
    echo ""
else
    echo "✅ No global service variables found"
    echo ""
fi

# Check for proper Annotated usage
echo "5️⃣ Checking for proper type annotations with Depends()..."
missing_annotations=$(rg "=\s*Depends\(get_" backend/ --type py 2>/dev/null | grep -v "Annotated" | head -5 || true)
if [ -n "$missing_annotations" ]; then
    echo "⚠️  Found Depends() without Annotated type hints:"
    echo "$missing_annotations"
    echo "..."
    echo ""
else
    echo "✅ All Depends() usage has proper Annotated type hints"
    echo ""
fi

# Summary
echo "📊 Summary:"
echo "- Always use backend.core.dependencies_v2"
echo "- Use Annotated[Type, Depends(get_service)] pattern"
echo "- Avoid direct app.state access"
echo "- Let ServiceRegistry manage service lifecycle"
echo ""
echo "See .claude/instructions/service-patterns.md for migration guide"
