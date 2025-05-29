#!/bin/bash

# TV Mode Script
# Sets TV (HDMI-A-1) as primary display, disables desk monitor, and changes audio to TV

# Use KDE's kscreen-doctor to manage displays
# Get current display config
echo "Current KScreen config:"
kscreen-doctor -o > /tmp/kscreen_config.txt

# Force a reset of the display configuration
echo "Resetting display configuration..."
kscreen-doctor configure

# Check if HDMI-A-1 is detected by KScreen
if grep -A 2 "HDMI-A-1" /tmp/kscreen_config.txt | grep "connected" > /dev/null; then
  echo "HDMI-A-1 is connected, switching to TV mode"
  
  # Enable HDMI-A-1 and set as primary
  echo "Enabling HDMI-A-1 output"
  kscreen-doctor output.HDMI-A-1.enable output.HDMI-A-1.primary
  
  # Sleep briefly to let the first change apply
  sleep 1
  
  # Then disable DP-1
  echo "Disabling DP-1 output"
  kscreen-doctor output.DP-1.disable
  
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
