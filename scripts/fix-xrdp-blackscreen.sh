#!/usr/bin/env bash
# Corrige pantalla negra xrdp: env X11, reconnectwm, reinicia sesiones.
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  exec sudo bash "$0" "$@"
fi

USER_NAME="${SUDO_USER:-mauro}"
USER_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6)"

apt-get install -y xfwm4 xfdesktop4 dbus-x11 >/dev/null

cat > "$USER_HOME/.xsessionrc" <<'EOF'
export XDG_SESSION_TYPE=x11
export GDK_BACKEND=x11
EOF
chown "$USER_NAME:$USER_NAME" "$USER_HOME/.xsessionrc"

echo xfce4-session > "$USER_HOME/.xsession"
chown "$USER_NAME:$USER_NAME" "$USER_HOME/.xsession"

cat > /etc/xrdp/startwm.sh <<'EOF'
#!/bin/sh
unset DBUS_SESSION_BUS_ADDRESS
unset XDG_RUNTIME_DIR
if [ -r /etc/default/locale ]; then
  . /etc/default/locale
  export LANG LANGUAGE
fi
export XDG_SESSION_TYPE=x11
export GDK_BACKEND=x11
exec startxfce4
EOF
chmod +x /etc/xrdp/startwm.sh

cat > /etc/xrdp/reconnectwm.sh <<'EOF'
#!/bin/sh
export XDG_SESSION_TYPE=x11
export GDK_BACKEND=x11
exec startxfce4
EOF
chmod +x /etc/xrdp/reconnectwm.sh

# Cerrar sesiones RDP colgadas del usuario
pkill -u "$USER_NAME" -f 'Xorg :1[0-9]' 2>/dev/null || true
pkill -u "$USER_NAME" xfce4-session 2>/dev/null || true
sleep 1

systemctl restart xrdp xrdp-sesman
echo "xrdp reiniciado. Reconecta desde Windows (cierra mstsc y abre de nuevo)."
