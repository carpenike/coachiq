# Setup Instructions

## Hardware Requirements

- **Raspberry Pi 4** (2GB+ RAM recommended)
- **CAN interface** - PiCAN2 or similar CAN HAT
- **Power supply** - 12V to 5V converter for Pi power
- **Wiring** - Proper gauge wire for CAN connections
- **SD Card** - 16GB+ for OS and application

## Hardware Setup

### 1. CAN Interface Installation

1. Install CAN HAT on Raspberry Pi GPIO pins
2. Set jumpers for 120Ω termination if at end of bus
3. Connect to RV CAN bus:
   - CAN-H to CAN-H (typically white)
   - CAN-L to CAN-L (typically blue)
   - Ground to chassis ground

### 2. Power Connection

1. Install 12V to 5V converter near Pi location
2. Connect to switched 12V source (fused appropriately)
3. Use proper connectors - no wire nuts in RV!

## Software Installation

### 1. Raspberry Pi OS Setup

```bash
# Flash Raspberry Pi OS Lite (64-bit) to SD card
# Enable SSH during flashing
# Boot Pi and connect via SSH
```

### 2. Enable CAN Interface

```bash
# Edit boot config
sudo nano /boot/config.txt

# Add these lines for PiCAN2:
dtparam=spi=on
dtoverlay=mcp2515-can0,oscillator=16000000,interrupt=25
dtoverlay=spi-bcm2835-overlay

# Reboot
sudo reboot
```

### 3. Install Dependencies

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python and Git
sudo apt install -y python3-pip python3-venv git

# Install CAN utilities
sudo apt install -y can-utils

# Install Poetry
curl -sSL https://install.python-poetry.org | python3 -
```

### 4. Clone and Install CoachIQ

```bash
# Clone repository
git clone https://github.com/yourusername/coachiq.git
cd coachiq

# Install backend dependencies
poetry install

# Install frontend dependencies
cd frontend
npm install
cd ..
```

### 5. Configure CAN Interface

```bash
# Create CAN interface config
sudo nano /etc/network/interfaces.d/can0

# Add:
auto can0
iface can0 inet manual
    pre-up /sbin/ip link set can0 type can bitrate 250000
    up /sbin/ifconfig can0 up
    down /sbin/ifconfig can0 down
```

### 6. Set Up Environment

```bash
# Copy example environment
cp .env.example .env

# Edit configuration
nano .env

# Key settings:
COACHIQ_CAN__INTERFACES=can0
COACHIQ_SERVER__HOST=0.0.0.0
COACHIQ_SERVER__PORT=8080
```

### 7. Test CAN Connection

```bash
# Bring up CAN interface
sudo ifconfig can0 up

# Test CAN reception
candump can0

# You should see RV-C messages scrolling by
```

### 8. Run CoachIQ

```bash
# Start backend
poetry run python run_server.py

# In another terminal, start frontend (development)
cd frontend
npm run dev

# Or build for production
npm run build
```

### 9. Set Up as Service (Optional)

```bash
# Create systemd service
sudo nano /etc/systemd/system/coachiq.service

# Add service configuration (see example below)
# Enable service
sudo systemctl enable coachiq
sudo systemctl start coachiq
```

## Example Systemd Service

```ini
[Unit]
Description=CoachIQ RV Control System
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/coachiq
ExecStart=/home/pi/.local/bin/poetry run python run_server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## Verification

1. Access web UI at `http://raspberrypi.local:8080`
2. Check for connected devices in the Entities page
3. Try controlling a light or other simple device
4. Monitor logs: `journalctl -u coachiq -f`

## Next Steps

- Read the [Usage Guide](usage.md) to learn the interface
- Check [Troubleshooting](troubleshooting.md) if things don't work
- Review [Safety Information](safety.md) before going live
