#!/bin/bash
# Command: /check-async-patterns
# Description: Verify proper async/await patterns and identify blocking operations

set -euo pipefail

echo "⚡ Checking Async/Await Patterns..."
echo ""

# Check for sync functions that should be async
echo "1️⃣ Checking for I/O operations in sync functions..."
sync_io=$(rg "def (?!.*async)[^_]\w+\(" backend/ --type py -A 5 | grep -B 5 -E "(\.read\(|\.write\(|requests\.|\.execute\(|\.query\(|\.save\(|\.load\()" | grep "def " | grep -v -E "(test_|mock_|@property)" | head -10 || true)

if [ -n "$sync_io" ]; then
    echo "⚠️  Found sync functions with I/O operations (should be async):"
    echo "$sync_io"
    echo ""
else
    echo "✅ No obvious sync I/O operations found"
    echo ""
fi

# Check for missing await keywords
echo "2️⃣ Checking for missing await keywords..."
missing_await=$(rg "async def" backend/ --type py -A 20 | grep -E "(get_.*\(|create_.*\(|update_.*\(|delete_.*\(|save\(|load\()" | grep -v -E "(await|return.*await|\s+#|def )" | head -10 || true)

if [ -n "$missing_await" ]; then
    echo "⚠️  Potential missing await keywords:"
    echo "$missing_await"
    echo ""
else
    echo "✅ No obvious missing awaits found"
    echo ""
fi

# Check for blocking sleep calls
echo "3️⃣ Checking for blocking sleep calls..."
blocking_sleep=$(rg "time\.sleep\(" backend/ --type py | grep -v -E "(test_|mock_|# Allow)" | head -5 || true)

if [ -n "$blocking_sleep" ]; then
    echo "❌ Found blocking time.sleep() calls:"
    echo "$blocking_sleep"
    echo ""
    echo "💡 Use 'await asyncio.sleep()' instead"
else
    echo "✅ No blocking sleep calls found"
    echo ""
fi

# Check for proper asyncio patterns
echo "4️⃣ Checking asyncio usage patterns..."

# Check for create_task without proper handling
orphan_tasks=$(rg "create_task\(" backend/ --type py -B 2 -A 2 | grep -B 2 -A 2 -v -E "(await|\.add_done_callback|background_tasks|self\.tasks)" | grep "create_task" | head -5 || true)

if [ -n "$orphan_tasks" ]; then
    echo "⚠️  Found create_task without proper handling:"
    echo "$orphan_tasks"
    echo "Store tasks and await/cancel them properly"
    echo ""
else
    echo "✅ Async tasks appear properly managed"
    echo ""
fi

# Check for synchronous context managers in async functions
echo "5️⃣ Checking for sync context managers in async functions..."
sync_context=$(rg "async def" backend/ --type py -A 10 | grep -B 5 "with open\(|with.*Lock\(\)|with.*\:" | grep -B 5 -v "async with" | grep "with " | head -5 || true)

if [ -n "$sync_context" ]; then
    echo "⚠️  Found sync context managers in async functions:"
    echo "$sync_context"
    echo "Use 'async with' for async context managers"
    echo ""
else
    echo "✅ Context managers properly async"
    echo ""
fi

# Check for asyncio.run in web context
echo "6️⃣ Checking for asyncio.run() in web handlers..."
asyncio_run=$(rg "asyncio\.run\(" backend/ --type py | grep -v -E "(test_|__main__|cli\.py|scripts/)" | head -5 || true)

if [ -n "$asyncio_run" ]; then
    echo "❌ Found asyncio.run() in web context (causes nested loop error):"
    echo "$asyncio_run"
    echo ""
else
    echo "✅ No asyncio.run() in web handlers"
    echo ""
fi

# Check WebSocket async patterns
echo "7️⃣ Checking WebSocket async patterns..."
ws_blocking=$(rg "websocket\.(send|receive|accept|close)" backend/websocket/ --type py | grep -v await | head -5 || true)

if [ -n "$ws_blocking" ]; then
    echo "⚠️  WebSocket operations missing await:"
    echo "$ws_blocking"
    echo ""
else
    echo "✅ WebSocket operations properly awaited"
    echo ""
fi

# Summary
echo "⚡ Async Best Practices:"
echo "- Use 'async def' for any function doing I/O"
echo "- Always 'await' async function calls"
echo "- Replace time.sleep() with asyncio.sleep()"
echo "- Store and manage background tasks properly"
echo "- Use 'async with' for async context managers"
echo "- Never use asyncio.run() inside web handlers"
echo "- Always await WebSocket operations"
echo ""
echo "💡 Run 'poetry run pyright backend' to catch async type errors"
