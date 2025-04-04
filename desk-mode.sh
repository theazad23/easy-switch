#!/bin/bash

# Desk Mode Script
# Sets desk monitor (DP-1) as primary display, disables TV, and changes audio to desk speakers

# Use KDE's kscreen-doctor to manage displays
# Get current display config
echo "Current KScreen config:"
kscreen-doctor -o > /tmp/kscreen_config.txt

# Force a reset of the display configuration
echo "Resetting display configuration..."
kscreen-doctor configure

# Check if DP-1 is detected by KScreen
if grep -A 2 "DP-1" /tmp/kscreen_config.txt | grep "connected" > /dev/null; then
  echo "DP-1 is connected, switching to desk mode"
  
  # Enable DP-1 and set as primary
  echo "Enabling DP-1 output"
  kscreen-doctor output.DP-1.enable output.DP-1.primary
  
  # Sleep briefly to let the first change apply
  sleep 1
  
  # Then disable HDMI-A-1
  echo "Disabling HDMI-A-1 output"
  kscreen-doctor output.HDMI-A-1.disable
  
  # Set desk audio (Creative Pebble Pro)
  echo "Switching audio to desk speakers (Creative Pebble Pro)"
  pactl set-default-sink alsa_output.usb-Creative_Technology_Ltd_Creative_Pebble_Pro_MF1710-01.analog-stereo
  
  # Notify user
  notify-send "Desk Mode Activated" "Display and audio switched to desk"
else
  echo "DP-1 not detected as connected"
  # DP-1 not connected, just switch audio
  echo "Switching audio to desk speakers (Creative Pebble Pro)"
  pactl set-default-sink alsa_output.usb-Creative_Technology_Ltd_Creative_Pebble_Pro_MF1710-01.analog-stereo
  
  # Notify user
  notify-send "Desk Mode Partial" "DP-1 not connected. Only audio switched to desk."
fi
