# Easy Switch

A collection of scripts for quickly switching between different display and audio configurations on multiple setups. These scripts use KDE's `kscreen-doctor` for display management and `pactl` for audio device switching.

## Repository Structure

- `living-room/`: Scripts for the living room PC setup
  - `desk-mode.sh`: Enables desk monitor (DP-1) as primary and sets audio to desk speakers (Creative Pebble Pro)
  - `tv-mode.sh`: Enables TV display (HDMI-A-1) as primary and sets audio to TV (navi 7)

- `basement/`: Scripts for the basement PC setup with triple monitors
  - `couch-mode.sh`: Enables only the 4K display (HDMI-A-1) and sets audio to HDA NVidia Pro
  - `desk-mode.sh`: Enables DP-3 as primary and DP-2 in portrait mode, sets audio to headphones (Arctis Nova Pro Wireless)
  - `all-mode.sh`: Enables all three monitors with their correct positions, with DP-3 as primary, and sets audio to headphones

## Basement Setup Details

### Display Configuration
- **HDMI-A-1**: 4K display, positioned at 1440,0
- **DP-3**: 1440p display at 165Hz, primary monitor for desk mode, positioned at 1440,560
- **DP-2**: 1440p display in portrait orientation (requires rotation.right), positioned at 0,0

### Audio Devices
- **HDA NVidia Pro** (alsa_output.pci-0000_01_00.1.pro-output-3): Main output for couch mode
- **Arctis Nova Pro Wireless** (alsa_output.usb-SteelSeries_Arctis_Nova_Pro_Wireless-00.pro-output-0): Headphones for desk mode

## Living Room Setup Details

### Display Configuration
- **DP-1**: Desk monitor
- **HDMI-A-1**: TV display

### Audio Devices
- **Creative Pebble Pro** (alsa_output.usb-Creative_Technology_Ltd_Creative_Pebble_Pro_MF1710-01.analog-stereo): Desk speakers
- **navi 7** (alsa_output.pci-0000_08_00.1.pro-output-7): TV audio

## Usage

Each script can be assigned to a KDE keyboard shortcut for quick switching between modes. The scripts will:

1. Check which displays are connected
2. Configure the displays according to the selected mode
3. Switch the audio output to the appropriate device
4. Notify the user of the changes made

If a required display is not connected, the scripts will either:
- Make no changes and notify the user (for primary displays)
- Skip that display but continue with other changes (for secondary displays)
- At minimum, switch the audio device even if display changes cannot be made

## Requirements

- KDE Plasma desktop environment
- `kscreen-doctor` (part of KDE)
- `pactl` for PulseAudio control
- `notify-send` for desktop notifications
