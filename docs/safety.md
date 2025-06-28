# Safety Information

## Important Safety Considerations

This system connects to your RV's electrical and control systems. While designed to be safe, improper installation or use could cause problems. Please read and understand these safety guidelines.

## Electrical Safety

### Before Installation

⚡ **ALWAYS disconnect RV from shore power AND turn off battery disconnect**

- RV systems run on 12V DC but can still cause shorts, sparks, or fires
- CAN bus typically carries low voltage but shares grounds with 12V systems
- Never work on wiring with power connected

### Wiring Guidelines

1. **Use proper wire gauge**
   - CAN bus: 20-22 AWG twisted pair
   - Power connections: Follow 12V DC wiring standards
   - Never use solid core wire in RV (vibration causes breaks)

2. **Secure all connections**
   - Use proper connectors (no wire nuts in RVs!)
   - Strain relief on all connections
   - Protect wires from sharp edges and heat

3. **Fuse everything**
   - Add inline fuse for Pi power (2-3A)
   - Never tap directly into high-current circuits
   - Use existing fuse panels when possible

## System Safety

### What This System Controls

✅ **Safe to automate:**
- Interior lights
- Exhaust fans
- Tank level monitoring
- Battery monitoring
- HVAC (with built-in safeties)
- Awning lights

⚠️ **Use with caution:**
- Slide-outs (ensure clear path)
- Awnings (check weather)
- Water pumps (monitor for leaks)
- Exterior lights (legal requirements)

❌ **Never automate:**
- Propane systems
- Engine/transmission
- Brakes or steering
- Jacks/leveling (without supervision)
- Generator auto-start (CO poisoning risk)

### Testing New Controls

1. **Always test with manual override available**
2. **Start with non-critical systems** (interior lights)
3. **Verify controls work as expected** before relying on them
4. **Document any unexpected behavior**

## Operational Safety

### System Limitations

- **This is convenience automation, not safety-critical**
- Physical switches should always override automation
- Don't rely solely on app for critical functions
- System may have delays or miss commands

### Failure Modes

**If the system fails:**
- All devices return to manual control
- No devices should be "stuck" in any state
- Power cycle (turn off/on) resolves most issues
- Physical switches always work

### Emergency Procedures

**If something goes wrong:**

1. **Immediate:** Use physical switch/breaker
2. **Short term:** Power down Raspberry Pi
3. **If needed:** Disconnect CAN interface
4. **Last resort:** Pull fuse or disconnect battery

## Installation Safety Checklist

Before powering up:

- [ ] All connections secure and insulated
- [ ] No bare wires or shorts possible
- [ ] Fuses installed on power connections
- [ ] CAN termination resistors correct (120Ω)
- [ ] Physical clearance around Pi for cooling
- [ ] Manual overrides accessible
- [ ] Tested with multimeter for shorts

## Specific Warnings

### Slide-Out Safety
- **Never** operate slides without checking clearance
- Automation should include position sensors
- Always have someone watching during operation
- Know location of manual override

### Propane Systems
- RV-C may show propane levels/status
- **Never** attempt to control valves remotely
- Propane requires physical presence for safety

### Generator Control
- Auto-start is dangerous (CO poisoning)
- Only monitor status, don't control
- Ensure CO detectors are working

### While Driving
- System not designed for use while driving
- Disable slide/awning controls when in motion
- Some states prohibit device use while driving

## Best Practices

1. **Document your installation**
   - Take photos of wiring
   - Note which fuses used
   - Mark CAN bus connections

2. **Regular checks**
   - Inspect wiring for chafing
   - Verify connections tight
   - Test manual overrides monthly

3. **Educate users**
   - Show others how to disable system
   - Explain manual overrides
   - Post emergency procedures

## Legal Considerations

- You modify your RV at your own risk
- May void warranties
- Check insurance implications
- Some states have specific RV modification laws
- You're responsible for safe operation

## Remember

This is a hobbyist project for convenience. It's not designed, tested, or certified for safety-critical operations. When in doubt:

1. Use manual controls
2. Consult professionals
3. Prioritize safety over convenience

**The author(s) assume no liability for use of this system. You are responsible for safe installation and operation.**
