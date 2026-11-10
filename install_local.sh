#!/usr/bin/env bash
# ==============================================================================
# 🖨️ SCANNERPAN - INSTALLAZIONE / AGGIORNAMENTO LOCALE NEL SISTEMA (Ubuntu / Debian)
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

echo "🔨 [ScannerPan] Compilazione pacchetto Debian aggiornato..."
./build_deb.sh >/dev/null

DEB_PKG=$(ls -t "${SCRIPT_DIR}/uploads"/scannerpan_*_amd64.deb | head -n 1)

echo "🚀 [ScannerPan] Installazione locale del pacchetto ${DEB_PKG} nel sistema..."
sudo dpkg -i "${DEB_PKG}"
sudo update-desktop-database /usr/share/applications 2>/dev/null || true
sudo gtk-update-icon-cache /usr/share/icons/hicolor 2>/dev/null || true

echo "✅ [ScannerPan] Installazione locale completata con successo! (versione pronta in /usr/bin/scannerpan)"
