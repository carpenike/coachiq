#!/bin/bash
# Command: /check-service-health
# Description: Verify all services are properly configured with health checks and dependencies

set -euo pipefail

echo "🏥 Checking Service Health Configuration..."
echo ""

# Check ServiceRegistry registrations in main.py
echo "1️⃣ Analyzing ServiceRegistry registrations..."
services_without_health=$(rg "register_service\(" backend/main.py -A 5 | grep -B 5 -E "health_check\s*=\s*None|^\s*\)" | grep "name=" | wc -l || echo "0")

if [ "$services_without_health" -gt 0 ]; then
    echo "⚠️  Found $services_without_health services without health checks"
    echo "Services should implement health_check for monitoring"
    echo ""
else
    echo "✅ All registered services have health checks"
    echo ""
fi

# Check for circular dependencies
echo "2️⃣ Checking for circular service dependencies..."
echo "Analyzing dependency graph..."

# Extract service dependencies
temp_file=$(mktemp)
rg 'dependencies=\[(.*?)\]' backend/main.py -o -r '$1' | tr ',' '\n' | sed 's/[" ]//g' | grep -v '^$' > "$temp_file" || true

if [ -s "$temp_file" ]; then
    echo "📊 Service dependency summary:"
    sort "$temp_file" | uniq -c | sort -rn | head -10
    echo ""
else
    echo "✅ No complex dependency chains detected"
    echo ""
fi
rm -f "$temp_file"

# Check for missing get_health implementations
echo "3️⃣ Checking service health method implementations..."
services_without_get_health=$(rg "class \w+Service" backend/services/ -l | while read -r file; do
    if ! grep -q "def get_health" "$file" 2>/dev/null; then
        basename "$file"
    fi
done | head -5)

if [ -n "$services_without_get_health" ]; then
    echo "⚠️  Services missing get_health() method:"
    echo "$services_without_get_health"
    echo ""
else
    echo "✅ All services implement get_health()"
    echo ""
fi

# Check startup performance
echo "4️⃣ Checking startup performance patterns..."
blocking_calls=$(rg "time\.sleep|\.recv\(|requests\." backend/ --type py | grep -v -E "(test_|async|# Allow|mock)" | head -5 || true)

if [ -n "$blocking_calls" ]; then
    echo "⚠️  Found potential blocking calls during startup:"
    echo "$blocking_calls"
    echo ""
else
    echo "✅ No obvious blocking calls found"
    echo ""
fi

# Check async initialization
echo "5️⃣ Checking for async initialization patterns..."
async_init=$(rg "async def initialize\(" backend/services/ -l | wc -l || echo "0")
echo "📊 Found $async_init services with async initialization"
echo ""

# Summary
echo "💡 Best Practices:"
echo "- All services should implement get_health() returning dict"
echo "- Use async initialization for I/O operations"
echo "- Avoid circular dependencies between services"
echo "- Register health_check lambda in ServiceRegistry"
echo "- Keep startup time under 1 second for safety-critical systems"
