#!/bin/bash
# Command: /show-service-deps
# Description: Visualize service dependencies and startup order

set -euo pipefail

echo "🔗 Service Dependency Graph"
echo "═══════════════════════════"
echo ""

# Extract service registrations from main.py
temp_file=$(mktemp)
temp_deps=$(mktemp)

# Find all service registrations
echo "📊 Registered Services and Dependencies:"
echo ""

# Parse service registrations
rg 'service_registry\.register_service\(' backend/main.py -A 10 | \
awk '
/register_service\(/ {
    in_registration = 1
    name = ""
    deps = ""
}
in_registration && /name=/ {
    match($0, /name="([^"]+)"/, arr)
    if (arr[1]) name = arr[1]
}
in_registration && /dependencies=\[/ {
    match($0, /dependencies=\[(.*?)\]/, arr)
    if (arr[1]) {
        deps = arr[1]
        gsub(/[" ]/, "", deps)
    }
}
in_registration && /\)/ {
    if (name) {
        if (deps) {
            print name ":" deps
        } else {
            print name ":none"
        }
    }
    in_registration = 0
}
' > "$temp_deps"

# Display services grouped by dependency level
echo "🏗️  Service Initialization Order:"
echo ""

# Find services with no dependencies (Level 0)
echo "Level 0 (No dependencies):"
while IFS=: read -r service deps; do
    if [ "$deps" = "none" ] || [ -z "$deps" ]; then
        echo "  ▸ $service"
        echo "$service" >> "$temp_file"
    fi
done < "$temp_deps"
echo ""

# Find services by dependency level
level=1
while [ $level -lt 10 ]; do  # Max 10 levels to prevent infinite loop
    found=0
    echo "Level $level:"

    while IFS=: read -r service deps; do
        if [ "$deps" != "none" ] && [ -n "$deps" ]; then
            # Check if all dependencies are already processed
            all_deps_ready=1
            IFS=',' read -ra dep_array <<< "$deps"
            for dep in "${dep_array[@]}"; do
                if ! grep -q "^$dep$" "$temp_file" 2>/dev/null; then
                    all_deps_ready=0
                    break
                fi
            done

            # If all dependencies ready and not already processed
            if [ $all_deps_ready -eq 1 ] && ! grep -q "^$service$" "$temp_file" 2>/dev/null; then
                echo "  ▸ $service → [$deps]"
                echo "$service" >> "$temp_file"
                found=1
            fi
        fi
    done < "$temp_deps"

    [ $found -eq 0 ] && break
    echo ""
    ((level++))
done

# Check for circular dependencies
echo "🔄 Circular Dependency Check:"
unprocessed=$(comm -23 <(cut -d: -f1 "$temp_deps" | sort) <(sort "$temp_file") 2>/dev/null || true)
if [ -n "$unprocessed" ]; then
    echo "⚠️  Potential circular dependencies detected:"
    echo "$unprocessed"
else
    echo "✅ No circular dependencies detected"
fi
echo ""

# Show service statistics
echo "📈 Service Statistics:"
total_services=$(wc -l < "$temp_deps")
no_deps=$(grep -c ":none" "$temp_deps" || echo "0")
with_deps=$((total_services - no_deps))

echo "  Total services: $total_services"
echo "  Independent services: $no_deps"
echo "  Dependent services: $with_deps"
echo "  Initialization levels: $level"
echo ""

# Most depended upon services
echo "🎯 Most Critical Services (most depended upon):"
cut -d: -f2 "$temp_deps" | tr ',' '\n' | grep -v "none" | sort | uniq -c | sort -rn | head -5 | \
while read count service; do
    echo "  $service - required by $count services"
done
echo ""

# Show access patterns
echo "🔌 Service Access Patterns:"
echo ""
echo "FastAPI Endpoints:"
echo "  from backend.core.dependencies_v2 import get_<service_name>"
echo "  service: Annotated[ServiceType, Depends(get_<service_name>)]"
echo ""
echo "Direct Access (startup/background tasks):"
echo "  service_registry.get_service('<service_name>')"
echo ""

# Cleanup
rm -f "$temp_file" "$temp_deps"

echo "💡 Tips:"
echo "- Services initialize in dependency order automatically"
echo "- Add health_check to monitor service status"
echo "- Use async initialize() for I/O operations"
echo "- See startup logs for actual initialization timing"
