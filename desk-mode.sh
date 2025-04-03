#!/bin/bash

# Desk Mode Script
# Sets desk monitor (DP-1) as primary display, disables TV, and changes audio to desk speakers

# Use KDE's kscreen-doctor to manage displays
# First check available outputs
xrandr > /tmp/xrandr_output.txt

# Force a reset of the display configuration
kscreen-doctor configure

# Check if DP-1 is connected
if grep "DP-1 connected" /tmp/xrandr_output.txt > /dev/null; then
  # Make sure DP-1 is enabled and set as primary
  kscreen-doctor output.DP-1.enable output.DP-1.primary
  
  # Sleep briefly to let the first change apply
  sleep 1
  
  # Then disable HDMI-A-1
  kscreen-doctor output.HDMI-A-1.disable
  
  # Set desk audio (Creative Pebble Pro)
  pactl set-default-sink alsa_output.usb-Creative_Technology_Ltd_Creative_Pebble_Pro_MF1710-01.analog-stereo
  
  # Notify user
  notify-send "Desk Mode Activated" "Display and audio switched to desk"
else
  # DP-1 not connected, just switch audio
  pactl set-default-sink alsa_output.usb-Creative_Technology_Ltd_Creative_Pebble_Pro_MF1710-01.analog-stereo
  
  # Notify user
  notify-send "Desk Mode Partial" "DP-1 not connected. Only audio switched to desk."
fi
