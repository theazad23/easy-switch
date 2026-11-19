#!/bin/bash
# Mount the NAS folder plex_media/games at /mnt/games (Steam art library and other
# game files shared between the PCs). Run once per PC: sudo ./mount-nas-games.sh
# Asks for the NAS (smithers) SMB login and stores it root-only in
# /etc/samba/nas-credentials. Safe to re-run.
set -euo pipefail
NAS=//192.168.10.101/plex_media
CRED=/etc/samba/nas-credentials
MNT=/mnt/games
OWNER=${SUDO_USER:-anthony_z}
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
command -v mount.cifs >/dev/null || pacman -S --needed --noconfirm cifs-utils

if [ ! -s "$CRED" ]; then
  read -rp "NAS user name: " u
  read -rsp "NAS password: " p; echo
  install -d -m 755 /etc/samba
  umask 077; printf 'username=%s\npassword=%s\n' "$u" "$p" > "$CRED"; chmod 600 "$CRED"
  unset p
fi

# Make sure plex_media/games/steam-art exists (mount the share root briefly).
tmp=$(mktemp -d)
mount -t cifs "$NAS" "$tmp" -o credentials=$CRED,vers=3.0,uid=$(id -u "$OWNER"),gid=$(id -g "$OWNER")
mkdir -p "$tmp/games/steam-art"
umount "$tmp"; rmdir "$tmp"

mkdir -p "$MNT"
line="$NAS/games $MNT cifs credentials=$CRED,uid=$(id -u "$OWNER"),gid=$(id -g "$OWNER"),iocharset=utf8,file_mode=0664,dir_mode=0775,vers=3.0,nofail,_netdev,x-systemd.automount,x-systemd.idle-timeout=600 0 0"
if ! grep -qE "^[^#]*[[:space:]]$MNT[[:space:]]" /etc/fstab; then
  cp /etc/fstab /etc/fstab.bak-$(date +%Y%m%d)
  echo "$line" >> /etc/fstab
fi
systemctl daemon-reload
systemctl restart "$(systemd-escape -p --suffix=automount "$MNT")"
ls "$MNT" && echo "OK: $MNT is the NAS games folder"
