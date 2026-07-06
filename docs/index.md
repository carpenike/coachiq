# CoachIQ - RV Control System

Control your RV systems from a web interface running on Raspberry Pi.

## Quick Start

1. Connect Raspberry Pi to RV CAN bus
2. Access web UI at http://raspberrypi.local:8000
3. Control lights, climate, tanks, etc.

## What is CoachIQ?

CoachIQ is a personal project that lets you monitor and control your RV's systems through a modern web interface. It connects to your RV's CAN bus to read sensor data and send control commands.

### Features

- **Real-time monitoring** - See tank levels, battery status, temperatures
- **Device control** - Turn lights on/off, adjust climate zones and heat sources
- **Power system** - Victron Cerbo GX integration: inverter/charger, generator, DC loads, shore power
- **Location** - GPS trip log with a breadcrumb map and GPX export
- **Web interface** - Access from any device on your RV's network
- **Raspberry Pi based** - Runs on affordable hardware

## Documentation

- [Setup Guide](setup.md) - Hardware requirements and installation
- [Usage Guide](usage.md) - How to use the system
- [Configuration Guide](configuration-guide.md) - Settings and environment variables
- [Troubleshooting](troubleshooting.md) - Common problems and solutions
- [Safety Information](safety.md) - Important safety considerations
- [API Reference](api/reference.md) - For custom integrations

## Quick Links

- Backend runs on port 8000
- Frontend dev server (if running separately) on port 5173
- Server-Sent Events stream (`/api/events`) for real-time updates
- REST API for all controls

## Support

This is a personal project. Feel free to open issues on GitHub if you're using it and run into problems.
