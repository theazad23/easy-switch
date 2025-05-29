#!/bin/bash

# Couch Mode for Basement PC
# Enables only the 4K display (HDMI-A-1) and sets audio to HDA NVidia Pro

# Use KDE's kscreen-doctor to manage displays
# Get current display config
echo "Current KScreen config:"
kscreen-doctor -o > /tmp/kscreen_config.txt

# Force a reset of the display configuration
echo "Resetting display configuration..."
kscreen-doctor configure

# Check if HDMI-A-1 is detected by KScreen
if grep -A 2 "HDMI-A-1" /tmp/kscreen_config.txt | grep "connected" > /dev/null; then
  echo "HDMI-A-1 is connected, switching to couch mode"
  
  # Enable HDMI-A-1 and set as primary
  echo "Enabling HDMI-A-1 output"
  kscreen-doctor output.HDMI-A-1.enable output.HDMI-A-1.primary output.HDMI-A-1.mode.3840x2160@60
  
  # Sleep briefly to let the first change apply
  sleep 1
  
  # Disable other displays if they are connected
  echo "Disabling other outputs"
  
  # Check if DP-3 is connected before trying to disable it
  if grep -A 2 "DP-3" /tmp/kscreen_config.txt | grep "connected" > /dev/null; then
    echo "Disabling DP-3"
    kscreen-doctor output.DP-3.disable
  fi
  
  # Check if DP-2 is connected before trying to disable it
  if grep -A 2 "DP-2" /tmp/kscreen_config.txt | grep "connected" > /dev/null; then
    echo "Disabling DP-2"
    kscreen-doctor output.DP-2.disable
  fi
  
  # Set audio to HDA NVidia Pro (main output)
  echo "Switching audio to HDA NVidia Pro"
  pactl set-default-sink alsa_output.pci-0000_01_00.1.hdmi-stereo
  
  # Notify user
  notify-send "Couch Mode Activated" "Display and audio switched for couch viewing"
else
  echo "HDMI-A-1 not detected as connected"
  # HDMI not connected, don't change any settings
  
  # Notify user
  notify-send "Couch Mode Failed" "HDMI-A-1 not connected. No changes made."
fi
