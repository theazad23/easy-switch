#!/bin/bash

# Desk Mode for Basement PC
# Disables the TV (HDMI-A-1) and enables both DP-3 and DP-2 (in portrait orientation)
# Sets audio to headphones (Arctis Nova Pro Wireless)

# Use KDE's kscreen-doctor to manage displays
# Get current display config
echo "Current KScreen config:"
kscreen-doctor -o > /tmp/kscreen_config.txt

# Force a reset of the display configuration
echo "Resetting display configuration..."
kscreen-doctor configure

# Check if primary monitor DP-3 is detected by KScreen
if grep -A 2 "DP-3" /tmp/kscreen_config.txt | grep "connected" > /dev/null; then
  echo "DP-3 is connected, switching to desk mode"
  
  # First, enable DP-3 as primary with exact position
  echo "Enabling DP-3 output as primary"
  kscreen-doctor output.DP-3.enable output.DP-3.primary output.DP-3.mode.2560x1440@165 output.DP-3.position.1440,560
  
  # Sleep briefly to let the change apply
  sleep 1
  
  # Check if left monitor DP-2 is also connected
  if grep -A 2 "DP-2" /tmp/kscreen_config.txt | grep "connected" > /dev/null; then
    echo "DP-2 is also connected, enabling it in portrait mode"
    kscreen-doctor output.DP-2.enable output.DP-2.mode.2560x1440@144 output.DP-2.rotation.right output.DP-2.position.0,0
    
    # Sleep briefly to let the changes apply
    sleep 1
  else
    echo "DP-2 is not connected, skipping it"
  fi
  
  # Now that primary display is enabled, disable HDMI-A-1
  echo "Disabling HDMI-A-1 output"
  kscreen-doctor output.HDMI-A-1.disable
  
  # Sleep briefly to let the change apply
  sleep 1
  
  # Set audio to headphones (Arctis Nova Pro Wireless)
  echo "Switching audio to headphones (Arctis Nova Pro Wireless)"
  pactl set-default-sink alsa_output.usb-SteelSeries_Arctis_Nova_Pro_Wireless-00.pro-output-0
  
  # Notify user
  notify-send "Desk Mode Activated" "Display and audio switched for desk use"
else
  echo "DP-3 not detected as connected"
  # Primary monitor not connected, don't change any settings
  
  # Notify user
  notify-send "Desk Mode Failed" "Primary monitor (DP-3) not connected. No changes made."
fi
