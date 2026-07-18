#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/tk-selection"
BACKEND_DIR="${APP_DIR}/backend"
SERVICE_FILE="/etc/systemd/system/tk-selection-backend.service"
ENV_DIR="/etc/tk-selection"
ENV_FILE="${ENV_DIR}/backend.env"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Please run as root: sudo bash deploy/install_backend_linux.sh"
  exit 1
fi

if ! id tkbackend >/dev/null 2>&1; then
  useradd --system --create-home --shell /usr/sbin/nologin tkbackend
fi

apt-get update
apt-get install -y python3 python3-venv python3-pip nginx libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libgbm1 libgtk-3-0 fonts-noto-cjk
apt-get install -y libasound2t64 || apt-get install -y libasound2

mkdir -p "${BACKEND_DIR}" "${ENV_DIR}"

if [[ ! -f "${ENV_FILE}" ]]; then
  cp "${APP_DIR}/deploy/backend.env.example" "${ENV_FILE}"
  chmod 600 "${ENV_FILE}"
  echo "Created ${ENV_FILE}. Edit it before starting the service."
fi

cd "${BACKEND_DIR}"
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright .venv/bin/python -m playwright install chromium

chown -R tkbackend:tkbackend "${APP_DIR}"
chown -R tkbackend:tkbackend /opt/ms-playwright
cp "${APP_DIR}/deploy/tk-selection-backend.service" "${SERVICE_FILE}"
systemctl daemon-reload
systemctl enable tk-selection-backend

echo "Backend installed."
echo "Next:"
echo "1. Edit ${ENV_FILE}"
echo "2. Configure nginx using deploy/nginx-tk-selection.conf"
echo "3. systemctl restart tk-selection-backend"
