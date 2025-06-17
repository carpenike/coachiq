#!/bin/bash
# Command: /check-safety-patterns
# Description: Verify safety-critical patterns for RV-C vehicle control

set -euo pipefail

echo "🚨 Checking Safety-Critical Patterns..."
echo ""

# Check for emergency stop implementation
echo "1️⃣ Verifying emergency stop capabilities..."
emergency_stop=$(rg "emergency.?stop|emergency_stop|emergencyStop" backend/ --type py -i | grep -v test_ | wc -l || echo "0")

if [ "$emergency_stop" -lt 3 ]; then
    echo "⚠️  Limited emergency stop implementation found ($emergency_stop references)"
    echo "Ensure emergency stop is accessible from multiple layers"
else
    echo "✅ Emergency stop implementation found ($emergency_stop references)"
fi
echo ""

# Check for safety validation in control endpoints
echo "2️⃣ Checking control endpoint safety validation..."
control_endpoints=$(rg "@router\.(post|put).*control" backend/api/ --type py -A 10 | grep -B 10 -E "(safety|validate|check|verify)" | grep "@router" | wc -l || echo "0")
total_control=$(rg "@router\.(post|put).*control" backend/api/ --type py | wc -l || echo "1")

if [ "$control_endpoints" -lt "$total_control" ]; then
    echo "⚠️  Some control endpoints may lack safety validation"
    echo "Found $control_endpoints validated out of $total_control control endpoints"

    echo ""
    echo "Unvalidated endpoints:"
    rg "@router\.(post|put).*control" backend/api/ --type py -B 2 | grep -B 2 -v -E "(safety|validate|check)" | grep "def " | head -5 || true
else
    echo "✅ All control endpoints appear to have safety validation"
fi
echo ""

# Check for command acknowledgment patterns
echo "3️⃣ Checking command/acknowledgment patterns..."
ack_patterns=$(rg "acknowledge|acknowledgment|confirm|pending_command" backend/ --type py | grep -v test_ | wc -l || echo "0")

if [ "$ack_patterns" -lt 5 ]; then
    echo "⚠️  Limited command acknowledgment patterns found"
    echo "Consider implementing command/ack for safety-critical operations"
else
    echo "✅ Command acknowledgment patterns detected ($ack_patterns instances)"
fi
echo ""

# Check for interlock patterns
echo "4️⃣ Checking safety interlock patterns..."
interlocks=$(rg "interlock|safety_check|can_operate|is_safe" backend/ --type py -i | grep -v test_ | head -10 || true)

if [ -z "$interlocks" ]; then
    echo "⚠️  No safety interlock patterns found"
    echo "Consider implementing interlocks for:"
    echo "  - Slides/awnings (park brake must be set)"
    echo "  - Leveling jacks (engine must be off)"
    echo "  - Generator (transfer switch interlock)"
else
    echo "✅ Safety interlock patterns found:"
    echo "$interlocks" | head -5
fi
echo ""

# Check for timeout patterns
echo "5️⃣ Checking operation timeout patterns..."
timeouts=$(rg "timeout|expire|max_duration" backend/ --type py | grep -v test_ | grep -E "(= \d+|< \d+|> \d+)" | head -5 || true)

if [ -z "$timeouts" ]; then
    echo "⚠️  No timeout patterns found for operations"
    echo "All motor/actuator operations should have timeouts"
else
    echo "✅ Timeout patterns found:"
    echo "$timeouts"
fi
echo ""

# Check for branded safety types
echo "6️⃣ Checking for branded safety-critical types..."
branded_types=$(rg "Temperature|Pressure|Speed|Voltage" backend/ --type py | grep -E "(Brand|NewType|TypeAlias)" | wc -l || echo "0")

if [ "$branded_types" -lt 3 ]; then
    echo "⚠️  Limited use of branded types for safety-critical values"
    echo "Use branded types to prevent unit confusion (mph vs kph, PSI vs kPa)"
else
    echo "✅ Branded types in use ($branded_types definitions)"
fi
echo ""

# Check for safety service
echo "7️⃣ Checking SafetyService implementation..."
if [ -f "backend/services/safety_service.py" ]; then
    echo "✅ SafetyService found"

    # Check for critical methods
    for method in "validate_operation" "emergency_stop" "check_interlocks" "get_safety_status"; do
        if rg "def $method" backend/services/safety_service.py > /dev/null 2>&1; then
            echo "  ✓ $method implemented"
        else
            echo "  ⚠️  $method missing"
        fi
    done
else
    echo "❌ SafetyService not found!"
    echo "Critical: Implement centralized safety validation"
fi
echo ""

# Summary
echo "🛡️ Safety-Critical Requirements:"
echo "- Emergency stop must be accessible and tested"
echo "- All control operations need safety validation"
echo "- Implement command/acknowledgment for critical operations"
echo "- Use interlocks (park brake, engine state, etc.)"
echo "- Set timeouts for all motor/actuator operations"
echo "- Use branded types for units (Temperature, Pressure, Speed)"
echo "- Centralize safety logic in SafetyService"
echo ""
echo "Remember: This is a vehicle control system. Safety failures can cause injury."
