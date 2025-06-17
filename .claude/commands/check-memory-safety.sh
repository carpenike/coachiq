#!/bin/bash
# Command: /check-memory-safety
# Description: Verify memory management patterns for real-time CAN bus operations

set -euo pipefail

echo "🧠 Checking Memory Safety Patterns..."
echo ""

# Check for unbounded collections
echo "1️⃣ Checking for unbounded collections (memory leaks)..."
unbounded=$(rg "\.append\(|\.add\(" backend/ --type py -B 2 -A 2 | grep -B 2 -A 2 -v -E "(maxlen=|if len\(|\.pop|FIFO|while len|[:1000]|test_)" | grep "\.append\(\|\.add\(" | head -10 || true)

if [ -n "$unbounded" ]; then
    echo "⚠️  Found potentially unbounded collections:"
    echo "$unbounded"
    echo ""
    echo "💡 Add FIFO limiting: if len(buffer) > MAX_SIZE: buffer.pop(0)"
else
    echo "✅ No obvious unbounded collections found"
fi
echo ""

# Check CAN buffer management
echo "2️⃣ Checking CAN message buffer patterns..."
can_buffers=$(rg "can_.*_log|sniffer_log|message_buffer" backend/ --type py -A 3 | grep -E "(append|deque)" | head -5 || true)

if [ -n "$can_buffers" ]; then
    echo "📊 CAN buffer patterns found:"
    echo "$can_buffers"
    echo ""

    # Check if they have size limits
    echo "Verifying size limits..."
    rg "can_.*_log|sniffer_log" backend/ --type py -A 5 | grep -E "(> \d+|maxlen=|pop\(0\))" | head -5 || echo "⚠️  Some buffers may lack size limits"
else
    echo "✅ No CAN buffer issues detected"
fi
echo ""

# Check for blocking CAN operations
echo "3️⃣ Checking for blocking CAN operations..."
blocking_can=$(rg "bus\.recv\(|can\.recv\(" backend/ --type py | grep -v -E "(AsyncBufferedReader|await|test_)" | head -5 || true)

if [ -n "$blocking_can" ]; then
    echo "❌ Found blocking CAN recv() calls:"
    echo "$blocking_can"
    echo ""
    echo "💡 Use AsyncBufferedReader with await instead:"
    echo "   reader = can.AsyncBufferedReader()"
    echo "   message = await reader.get_message()"
else
    echo "✅ No blocking CAN operations found"
fi
echo ""

# Check WebSocket memory cleanup
echo "4️⃣ Checking WebSocket connection cleanup..."
ws_cleanup=$(rg "active_connections|connected_clients" backend/websocket/ --type py -A 5 | grep -E "(remove|discard|pop|cleanup)" | wc -l || echo "0")

if [ "$ws_cleanup" -lt 3 ]; then
    echo "⚠️  Limited WebSocket cleanup patterns found"
    echo "Ensure disconnected clients are removed from active_connections"
else
    echo "✅ WebSocket cleanup patterns detected ($ws_cleanup instances)"
fi
echo ""

# Check for time-based cleanup
echo "5️⃣ Checking time-based data cleanup..."
time_cleanup=$(rg "time\.time\(\)|timestamp|age|expire" backend/ --type py -B 2 -A 2 | grep -B 2 -A 2 -E "(< |> |if.*time)" | grep -v test_ | head -5 || true)

if [ -n "$time_cleanup" ]; then
    echo "✅ Found time-based cleanup patterns"
else
    echo "💡 Consider time-based cleanup for short-lived data:"
    echo "   pending_commands = [cmd for cmd in pending_commands"
    echo "                      if time.time() - cmd['timestamp'] < 2.0]"
fi
echo ""

# Summary
echo "🛡️ Memory Safety Guidelines:"
echo "- Always limit collection sizes (deque(maxlen=1000) or manual FIFO)"
echo "- Use AsyncBufferedReader for CAN operations"
echo "- Clean up WebSocket connections on disconnect"
echo "- Implement time-based cleanup for temporary data"
echo "- Monitor memory usage in production with metrics"
