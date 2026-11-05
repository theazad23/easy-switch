#!/bin/sh
# Root half of the Gaming Mode setup: autologin + relogin, so switching between
# Plasma and Gaming Mode (a logout) lands straight in the other session.
#   sudo sh login-manager-setup.sh            (uses $SUDO_USER)
#   sudo sh login-manager-setup.sh <username>
# Supports Plasma Login (plasmalogin) and SDDM. Idempotent.
set -e
user="${1:-$SUDO_USER}"
[ -n "$user" ] || { echo "usage: sudo sh $0 [username]" >&2; exit 1; }
[ "$(id -u)" = 0 ] || { echo "run with sudo" >&2; exit 1; }

dm="$(systemctl show -p Id --value display-manager)"; dm="${dm%.service}"
echo "display manager: $dm  user: $user"

# Set KEY=VALUE inside [Autologin] of an ini file (create group/file as needed).
set_autologin() {  # set_autologin <file> <key> <value>
    f="$1"; k="$2"; v="$3"
    [ -f "$f" ] || printf '[Autologin]\n' > "$f"
    grep -q '^\[Autologin\]' "$f" || printf '\n[Autologin]\n' >> "$f"
    if awk '/^\[/{g=$0} g=="[Autologin]" && $0 ~ "^"k"=" {found=1} END{exit !found}' k="$k" "$f"; then
        awk -v k="$k" -v v="$v" '/^\[/{g=$0} g=="[Autologin]" && $0 ~ "^"k"=" {$0=k"="v} {print}' "$f" > "$f.tmp" && mv "$f.tmp" "$f"
    else
        sed -i "/^\[Autologin\]/a $k=$v" "$f"
    fi
}

case "$dm" in
plasmalogin)
    # Plasma Login reads ONLY /etc/plasmalogin.conf -- not /etc/plasmalogin.conf.d/.
    # (Learned the hard way on bonestorm: Relogin in conf.d was silently ignored.)
    main=/etc/plasmalogin.conf
    set_autologin "$main" User "$user"
    set_autologin "$main" Relogin true
    grep -q '^Session=' "$main" || set_autologin "$main" Session plasma.desktop

    # steamos-session-select / steam-set-session write the wanted session to
    # conf.d/zz-steamos-autologin.conf, which Plasma Login ignores. Copy its
    # Session= into the main file whenever it changes.
    cat > /usr/local/bin/plasmalogin-session-sync <<'EOS'
#!/bin/sh
s=$(sed -n 's/^Session=//p' /etc/plasmalogin.conf.d/zz-steamos-autologin.conf 2>/dev/null)
# only accept real installed session names
[ -n "$s" ] && [ -f "/usr/share/wayland-sessions/$s" ] || exit 0
sed -i "s/^Session=.*/Session=$s/" /etc/plasmalogin.conf
EOS
    chmod 755 /usr/local/bin/plasmalogin-session-sync
    cat > /etc/systemd/system/plasmalogin-session-sync.service <<'EOS'
[Unit]
Description=Copy SteamOS session choice into /etc/plasmalogin.conf

[Service]
Type=oneshot
ExecStart=/usr/local/bin/plasmalogin-session-sync
EOS
    cat > /etc/systemd/system/plasmalogin-session-sync.path <<'EOS'
[Unit]
Description=Watch SteamOS session choice for Plasma Login

[Path]
PathChanged=/etc/plasmalogin.conf.d/zz-steamos-autologin.conf

[Install]
WantedBy=multi-user.target
EOS
    mkdir -p /etc/plasmalogin.conf.d
    systemctl daemon-reload
    systemctl enable --now plasmalogin-session-sync.path
    /usr/local/bin/plasmalogin-session-sync
    echo "--- $main:"; cat "$main"
    ;;
sddm)
    # SDDM reads /usr/lib/sddm/sddm.conf.d, then /etc/sddm.conf.d/*.conf in order,
    # then /etc/sddm.conf LAST. steam-set-session writes
    # /etc/sddm.conf.d/zz-steamos-autologin.conf (Session=), so no sync is needed --
    # but any [Autologin] User/Session/Relogin left in /etc/sddm.conf overrides
    # conf.d and pins every relogin to that session (seen on lisa: Session=plasma).
    # Comment those keys out (backup once as /etc/sddm.conf.pre-gaming-mode).
    if [ -f /etc/sddm.conf ] && awk '/^\[/{g=$0} g=="[Autologin]" && /^(User|Session|Relogin)=/{f=1} END{exit !f}' /etc/sddm.conf; then
        [ -e /etc/sddm.conf.pre-gaming-mode ] || cp -a /etc/sddm.conf /etc/sddm.conf.pre-gaming-mode
        awk '/^\[/{g=$0} g=="[Autologin]" && /^(User|Session|Relogin)=/{$0="# moved to /etc/sddm.conf.d/50-autologin.conf (Gaming Mode): "$0} {print}' \
            /etc/sddm.conf > /etc/sddm.conf.tmp && mv /etc/sddm.conf.tmp /etc/sddm.conf
        echo "--- /etc/sddm.conf (autologin keys commented out):"; cat /etc/sddm.conf
    fi
    mkdir -p /etc/sddm.conf.d
    printf '[Autologin]\nUser=%s\nRelogin=true\nSession=plasma.desktop\n' "$user" > /etc/sddm.conf.d/50-autologin.conf
    echo "--- /etc/sddm.conf.d:"; for f in /etc/sddm.conf.d/*.conf; do echo "# $f"; cat "$f"; done
    ;;
*)
    echo "unsupported display manager '$dm' (need plasmalogin or sddm)" >&2; exit 1 ;;
esac
echo "done. Next login after a logout/reboot autologs into the session named above."
