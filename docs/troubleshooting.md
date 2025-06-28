# Troubleshooting Guide

## Common Issues and Solutions

### CAN Bus Connection Issues

#### No CAN messages received
```bash
# Check CAN interface is up
ifconfig can0

# If not shown, bring it up
sudo ifconfig can0 up

# Test raw CAN traffic
candump can0
```

**Solutions:**
- Verify wiring (CAN-H to CAN-H, CAN-L to CAN-L)
- Check termination resistors (120Ω at each end of bus)
- Ensure proper bitrate (RV-C uses 250kbps)
- Test with multimeter: ~2.5V between CAN-H and CAN-L at idle

#### CAN interface won't start
```bash
# Check kernel messages
dmesg | grep -i can

# Verify SPI is enabled
lsmod | grep spi

# Check boot config
cat /boot/config.txt | grep -E "spi|can"
```

### Web Interface Issues

#### Can't access web UI
1. **Check backend is running**
   ```bash
   # Check process
   ps aux | grep python | grep run_server

   # Check service status (if using systemd)
   sudo systemctl status coachiq

   # View logs
   journalctl -u coachiq -n 50
   ```

2. **Verify network connection**
   ```bash
   # Check Pi IP address
   ip addr show

   # Test from another device
   ping raspberrypi.local
   ```

3. **Check firewall**
   ```bash
   # Allow port 8080
   sudo ufw allow 8080
   ```

#### Page loads but no devices shown
- Wait 30-60 seconds - devices announce periodically
- Check WebSocket connection in browser console (F12)
- Verify CAN messages are being received (see above)

### Device Control Issues

#### Device not responding to commands
1. **Check physical device**
   - Is breaker/fuse on?
   - Does manual switch work?
   - Is device powered?

2. **Verify CAN communication**
   ```bash
   # Watch for device messages
   candump can0 | grep -i [DEVICE_ID]
   ```

3. **Check device compatibility**
   - Not all RV-C devices support remote control
   - Some require specific enable sequences
   - Consult device manual

#### Delayed or intermittent response
- Normal for some devices - RV-C has retry mechanisms
- Check for CAN bus errors: `ip -details -statistics link show can0`
- Reduce bus load - too many queries can saturate bus

### Performance Issues

#### High CPU usage
```bash
# Check CPU usage
top

# Monitor Python process
htop
```

**Solutions:**
- Restart service: `sudo systemctl restart coachiq`
- Check for runaway logging
- Reduce poll frequency in config

#### Memory issues
```bash
# Check memory
free -h

# Clear cache if needed
sudo sync && sudo sysctl -w vm.drop_caches=3
```

### Installation Issues

#### Poetry command not found
```bash
# Add Poetry to PATH
export PATH="$HOME/.local/bin:$PATH"

# Add to .bashrc
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
```

#### npm/node issues
```bash
# Install Node.js
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt-get install -y nodejs
```

### Debugging Tools

#### Enable debug logging
```bash
# Set in .env file
COACHIQ_LOG_LEVEL=DEBUG

# Restart service
sudo systemctl restart coachiq
```

#### Monitor CAN bus
```bash
# See all messages
candump can0

# Filter by PGN
candump can0 | grep "1FE"

# Log to file
candump -l can0
```

#### Check WebSocket
Open browser console (F12):
```javascript
// Check connection status
console.log(ws.readyState);

// Monitor messages
ws.onmessage = (e) => console.log(e.data);
```

## Error Messages

### "No CAN interfaces found"
- CAN interface not configured
- Run: `sudo ifconfig can0 up`
- Check /etc/network/interfaces.d/can0

### "Failed to connect to CAN bus"
- Permission issue: add user to `dialout` group
- Interface down: bring up with ifconfig
- Wrong interface name in config

### "WebSocket connection failed"
- Backend not running
- Firewall blocking port 8080
- Wrong URL in frontend config

## Getting Help

### Collect Diagnostic Info
```bash
# Create diagnostic bundle
cat > diag.sh << 'EOF'
#!/bin/bash
echo "=== System Info ==="
uname -a
echo -e "\n=== CAN Interface ==="
ifconfig can0
ip -details -statistics link show can0
echo -e "\n=== Service Status ==="
systemctl status coachiq
echo -e "\n=== Recent Logs ==="
journalctl -u coachiq -n 100 --no-pager
echo -e "\n=== CAN Traffic Sample ==="
timeout 5 candump can0
EOF

chmod +x diag.sh
./diag.sh > diagnostic_info.txt
```

### Common Quick Fixes

1. **Restart everything**
   ```bash
   sudo systemctl restart coachiq
   sudo ifconfig can0 down && sudo ifconfig can0 up
   ```

2. **Clear and rebuild**
   ```bash
   cd ~/coachiq
   poetry install
   cd frontend && npm install && npm run build
   ```

3. **Check the basics**
   - Is Pi powered?
   - Is CAN bus connected?
   - Can you ping the Pi?
   - Is the SD card full?

Remember: This is a hobby project. Sometimes things need a reboot!
