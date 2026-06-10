#!/usr/bin/env bash
# Configura escritorio remoto RDP (xrdp + XFCE) para acceder desde Windows.
# Ejecutar en Ubuntu: bash scripts/setup-xrdp.sh
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  exec sudo bash "$0" "$@"
fi

export DEBIAN_FRONTEND=noninteractive

echo "==> Actualizando paquetes..."
apt-get update -qq

echo "==> Instalando xrdp + XFCE..."
apt-get install -y xrdp xfce4 xfce4-goodies dbus-x11

USER_NAME="${SUDO_USER:-mauro}"
USER_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6)"

echo "==> Configurando sesión XFCE para $USER_NAME..."
echo xfce4-session > "$USER_HOME/.xsession"
chown "$USER_NAME:$USER_NAME" "$USER_HOME/.xsession"

echo "==> Configurando /etc/xrdp/startwm.sh..."
STARTWM=/etc/xrdp/startwm.sh
cp -a "$STARTWM" "${STARTWM}.bak-$(date +%Y%m%d%H%M%S)"

cat > "$STARTWM" <<'EOF'
#!/bin/sh
if [ -r /etc/default/locale ]; then
  . /etc/default/locale
  export LANG LANGUAGE
fi
startxfce4
EOF
chmod +x "$STARTWM"

echo "==> Añadiendo xrdp al grupo ssl-cert..."
adduser xrdp ssl-cert 2>/dev/null || true

echo "==> Habilitando e iniciando xrdp..."
systemctl enable xrdp
systemctl restart xrdp

IP="$(hostname -I | awk '{print $1}')"
echo ""
echo "Listo. Desde Windows:"
echo "  1. Win+R -> mstsc -> Enter"
echo "  2. Equipo: $IP  (hostname: $(hostname))"
echo "  3. Usuario: $USER_NAME + tu contraseña de Ubuntu"
echo ""
systemctl is-active xrdp && ss -tlnp | grep ':3389' || echo "AVISO: revisa systemctl status xrdp"
