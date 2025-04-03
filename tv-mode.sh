#!/bin/bash

# TV Mode Script
# Sets TV (HDMI-A-1) as primary display, disables desk monitor, and changes audio to TV

# Use KDE's kscreen-doctor to manage displays
# First check available outputs and display debug info
echo "Checking displays..."
xrandr | grep "connected" > /tmp/xrandr_output.txt
cat /tmp/xrandr_output.txt

# Try to get current display config
echo "Current KScreen config:"
kscreen-doctor -o

# Force a reset of the display configuration
echo "Resetting display configuration..."
kscreen-doctor configure

# Check if HDMI-A-1 is connected
if grep "HDMI-A-1 connected" /tmp/xrandr_output.txt > /dev/null; then
  echo "HDMI-A-1 is connected, switching to TV mode"
  
  # Try a different approach - use explicit monitor IDs instead of names
  echo "Identifying outputs..."
  OUTPUTS=$(kscreen-doctor -o | grep "Output" | cut -d " " -f2)
  
  # Find the ID of the HDMI-A-1 output
  for OUTPUT in $OUTPUTS; do
    if kscreen-doctor output.$OUTPUT.name | grep HDMI > /dev/null; then
      HDMI_ID=$OUTPUT
      echo "Found HDMI output ID: $HDMI_ID"
    elif kscreen-doctor output.$OUTPUT.name | grep DP > /dev/null; then
      DP_ID=$OUTPUT
      echo "Found DP output ID: $DP_ID"
    fi
  done
  
  if [ -n "$HDMI_ID" ]; then
    echo "Enabling HDMI output $HDMI_ID"
    kscreen-doctor output.$HDMI_ID.enable output.$HDMI_ID.primary
    
    # Sleep briefly to let the first change apply
    sleep 1
    
    if [ -n "$DP_ID" ]; then
      echo "Disabling DP output $DP_ID"
      kscreen-doctor output.$DP_ID.disable
    fi
  else
    echo "Could not find HDMI output ID"
    # Fall back to using direct names if IDs not found
    echo "Falling back to direct names"
    kscreen-doctor output.HDMI-A-1.enable output.HDMI-A-1.primary
    sleep 1
    kscreen-doctor output.DP-1.disable
  fi
  
  # Set TV audio to navi 7
  echo "Switching audio to TV (navi 7)"
  pactl set-default-sink alsa_output.pci-0000_08_00.1.pro-output-7
  
  # Notify user
  notify-send "TV Mode Activated" "Display and audio switched to TV"
else
  echo "HDMI-A-1 not detected as connected"
  # HDMI not connected, just switch audio
  pactl set-default-sink alsa_output.pci-0000_08_00.1.pro-output-7
  
  # Notify user
  notify-send "TV Mode Partial" "HDMI-A-1 not connected. Only audio switched to TV."
fi
