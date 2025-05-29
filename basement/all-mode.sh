#!/bin/bash

# All Mode for Basement PC
# Enables all three monitors (DP-3 as primary, DP-2 in portrait, and HDMI-A-1)
# Sets audio to headphones (Arctis Nova Pro Wireless)

# Use KDE's kscreen-doctor to manage displays
# Get current display config
echo "Current KScreen config:"
kscreen-doctor -o > /tmp/kscreen_config.txt

# Force a reset of the display configuration
echo "Resetting display configuration..."
kscreen-doctor configure

# Sleep to let the reset take effect
sleep 2

# Get updated display config after reset
kscreen-doctor -o > /tmp/kscreen_config.txt

# Check which monitors are connected
DP3_CONNECTED=$(grep -A 2 "DP-3" /tmp/kscreen_config.txt | grep "connected" > /dev/null && echo "yes" || echo "no")
DP2_CONNECTED=$(grep -A 2 "DP-2" /tmp/kscreen_config.txt | grep "connected" > /dev/null && echo "yes" || echo "no")
HDMI_CONNECTED=$(grep -A 2 "HDMI-A-1" /tmp/kscreen_config.txt | grep "connected" > /dev/null && echo "yes" || echo "no")

# Check if at least one monitor is connected
if [ "$DP3_CONNECTED" = "yes" ] || [ "$DP2_CONNECTED" = "yes" ] || [ "$HDMI_CONNECTED" = "yes" ]; then
  echo "At least one monitor is connected, enabling all available monitors"
  
  # Try a completely different approach - configure all displays in a single command
  echo "Configuring all displays at once"
  
  # Build the command based on which displays are connected
  CMD="kscreen-doctor"
  
  if [ "$DP3_CONNECTED" = "yes" ]; then
    CMD="$CMD output.DP-3.enable output.DP-3.primary output.DP-3.mode.2560x1440@165 output.DP-3.position.1440,2160"
  fi
  
  if [ "$HDMI_CONNECTED" = "yes" ]; then
    CMD="$CMD output.HDMI-A-1.enable output.HDMI-A-1.mode.3840x2160@60 output.HDMI-A-1.position.1440,0"
  fi
  
  if [ "$DP2_CONNECTED" = "yes" ]; then
    CMD="$CMD output.DP-2.enable output.DP-2.mode.2560x1440@144 output.DP-2.rotation.right output.DP-2.position.0,1600"
  fi
  
  # Execute the combined command
  echo "Executing: $CMD"
  eval $CMD
  
  # Sleep to let the changes apply
  sleep 3
  
  # Force a refresh of the display configuration
  echo "Refreshing display configuration..."
  kscreen-doctor configure
  
  # Set audio to headphones (Arctis Nova Pro Wireless)
  echo "Switching audio to headphones (Arctis Nova Pro Wireless)"
  pactl set-default-sink alsa_output.usb-SteelSeries_Arctis_Nova_Pro_Wireless-00.pro-output-0
  
  # Notify user
  notify-send "All Mode Activated" "All available displays enabled and audio switched to headphones"
else
  echo "No monitors detected as connected"
  # No monitors connected, don't change any settings
  
  # Notify user
  notify-send "All Mode Failed" "No monitors detected. No changes made."
fi
