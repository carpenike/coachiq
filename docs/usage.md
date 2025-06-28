# Usage Guide

## Accessing the System

Once installed, access CoachIQ from any device on your RV's network:

- **URL**: `http://raspberrypi.local:8080` or `http://[PI-IP-ADDRESS]:8080`
- **No login required** for local network access
- Works on phones, tablets, laptops

## Main Interface

### Dashboard

The main dashboard shows:
- Connected devices status
- System health indicators
- Quick controls for common devices

### Entities Page

The entities page is where you'll spend most time:

1. **Device List** - All discovered RV-C devices
   - Lights (dimmable and on/off)
   - HVAC systems
   - Tank levels
   - Battery status
   - Slide-outs
   - Awnings

2. **Device Control**
   - Click device name to expand controls
   - Toggle switches for on/off devices
   - Sliders for dimmable lights
   - Status indicators update in real-time

3. **Filtering**
   - Filter by device type
   - Search by name
   - Show only controllable devices

### Control Examples

#### Turning Lights On/Off
1. Navigate to Entities
2. Find the light (e.g., "Bedroom Overhead")
3. Click the toggle switch
4. Light should respond within 1 second

#### Adjusting Dimmable Lights
1. Find dimmable light in list
2. Click to expand controls
3. Use slider to set brightness (0-100%)
4. Changes apply in real-time

#### Monitoring Tank Levels
1. Tank sensors appear automatically
2. Shows percentage full
3. Updates every few seconds
4. Color coding: Green (OK), Yellow (Low), Red (Critical)

#### HVAC Control
1. Find HVAC/thermostat device
2. View current temperature
3. Adjust set point with +/- buttons
4. Select heat/cool/auto mode
5. Fan speed controls if supported

## Advanced Features

### Bulk Control
1. Select multiple devices with checkboxes
2. Use bulk action buttons:
   - Turn all on/off
   - Set all to specific level

### WebSocket Real-Time Updates
- No need to refresh
- Device states update automatically
- See changes made from RV physical controls

### Device Groups (Future Feature)
- Group related devices
- Control entire areas at once
- Create scenes/presets

## Mobile Usage

The interface is mobile-responsive:
- Large touch targets
- Swipe-friendly lists
- Optimized for one-handed use
- Add to home screen for app-like experience

## Tips & Best Practices

1. **Name Your Devices**
   - Devices may have generic names initially
   - Future: Rename in settings for clarity

2. **Test Controls Safely**
   - Test slide-outs and awnings with clear space
   - Verify manual overrides still work
   - Start with non-critical systems

3. **Network Considerations**
   - Use static IP for Raspberry Pi
   - Ensure good WiFi coverage in RV
   - Consider cellular backup for remote access

4. **Power Management**
   - System uses minimal power
   - Safe to leave running 24/7
   - Automatically reconnects after power loss

## Common Tasks

### Check All Tank Levels
1. Go to Entities
2. Filter by "tank" or "level"
3. View all tank statuses at once

### Turn Off All Lights
1. Go to Entities
2. Filter by device type "Light"
3. Select all (checkbox in header)
4. Click "Turn Off Selected"

### Monitor Battery Status
1. Battery devices show voltage and percentage
2. Set up notifications for low battery (future)
3. Historical graphs available (future)

## Troubleshooting Quick Tips

- **Device not responding**: Check physical switch/breaker
- **Can't access web UI**: Verify network connection
- **Devices missing**: Some take time to announce on CAN bus
- **Slow updates**: Normal - RV-C has polling intervals

See [Troubleshooting Guide](troubleshooting.md) for detailed help.
