#!/bin/bash
# Command: /check-tech-debt
# Description: Find and categorize technical debt, TODOs, and areas needing attention

set -euo pipefail

echo "🔍 Analyzing Technical Debt..."
echo ""

# Count different types of markers
echo "📊 Technical Debt Summary:"
echo ""

# TODOs
todo_count=$(rg "TODO|FIXME|HACK|XXX" backend/ frontend/src/ --type py --type ts -g "*.tsx" -i | wc -l || echo "0")
echo "📝 TODO/FIXME markers: $todo_count"

# Type ignores
type_ignore_count=$(rg "type:\s*ignore|@ts-ignore|@ts-expect-error|# type: ignore" backend/ frontend/src/ | wc -l || echo "0")
echo "🤫 Type ignores: $type_ignore_count"

# Any types
any_type_count=$(rg ": Any|-> Any|: any|= Any\[" backend/ frontend/src/ --type py --type ts | grep -v "from typing import Any" | wc -l || echo "0")
echo "❓ Explicit Any types: $any_type_count"

# Deprecated code
deprecated_count=$(rg "@deprecated|DeprecationWarning|# Deprecated|// Deprecated" backend/ frontend/src/ -i | wc -l || echo "0")
echo "⚠️  Deprecated code: $deprecated_count"

# Commented code blocks
commented_code=$(rg "^[\s]*#.*\(" backend/ --type py | grep -v -E "(TODO|FIXME|NOTE|type:|pytest|Copyright|flake8)" | wc -l || echo "0")
echo "💬 Commented code: ~$commented_code lines"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Show high priority items
echo "🚨 High Priority Items (FIXME/HACK/XXX):"
rg "FIXME|HACK|XXX" backend/ frontend/src/ --type py --type ts -g "*.tsx" -n | head -10 || echo "None found ✅"
echo ""

# Show security-related TODOs
echo "🔒 Security-Related TODOs:"
rg "TODO.*security|TODO.*auth|TODO.*password|TODO.*token" backend/ frontend/src/ -i | head -5 || echo "None found ✅"
echo ""

# Show performance TODOs
echo "⚡ Performance-Related TODOs:"
rg "TODO.*performance|TODO.*optimize|TODO.*slow|TODO.*cache" backend/ frontend/src/ -i | head -5 || echo "None found ✅"
echo ""

# Check for error handling TODOs
echo "❌ Error Handling TODOs:"
rg "TODO.*error|TODO.*exception|TODO.*handle" backend/ frontend/src/ -i | head -5 || echo "None found ✅"
echo ""

# Find potentially unfinished code
echo "🚧 Potentially Unfinished Code:"
rg "pass\s*$|\.\.\..*$|raise NotImplementedError" backend/ --type py | grep -v -E "(abstract|test_|Protocol)" | head -10 || echo "None found ✅"
echo ""

# Check test coverage markers
echo "🧪 Test Coverage Gaps:"
rg "pragma: no cover|nocov|skip.*test|test.*skip" backend/ frontend/src/ | head -5 || echo "Good coverage ✅"
echo ""

# Migration markers
echo "🔄 Migration Markers:"
rg "MIGRATION|LEGACY|OLD|BACKWARD.*COMPAT" backend/ frontend/src/ -i | grep -v -E "(test_|\.md)" | head -10 || echo "None found ✅"
echo ""

# Areas with most TODOs
echo "📍 Files with Most TODOs:"
rg "TODO|FIXME" backend/ frontend/src/ --type py --type ts -g "*.tsx" -c | sort -t: -k2 -rn | head -10
echo ""

# Recent TODOs (if in git)
if [ -d .git ]; then
    echo "🕐 Recently Added TODOs (last 30 days):"
    git log --since="30 days ago" -p | grep -E "^\+.*TODO|^\+.*FIXME" | head -10 || echo "None in recent commits ✅"
    echo ""
fi

# Summary recommendations
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "💡 Recommendations:"

if [ "$todo_count" -gt 50 ]; then
    echo "- High number of TODOs ($todo_count). Schedule a debt reduction sprint."
fi

if [ "$type_ignore_count" -gt 20 ]; then
    echo "- Many type ignores ($type_ignore_count). Fix types for better safety."
fi

if [ "$any_type_count" -gt 30 ]; then
    echo "- Excessive Any types ($any_type_count). Add proper type annotations."
fi

if [ "$deprecated_count" -gt 10 ]; then
    echo "- Deprecated code present ($deprecated_count). Plan migration/removal."
fi

echo "- Use issue tracker for TODOs longer than a sprint"
echo "- Prioritize FIXME/HACK items as they indicate problems"
echo "- Add dates to TODOs: # TODO(2024-01-15): Description"
echo ""
echo "Run periodically to track technical debt trends 📈"
