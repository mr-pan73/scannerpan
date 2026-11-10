#!/usr/bin/env bash
# ==============================================================================
# 📦 SCANNERPAN - SCRIPT DI BUILD PACCHETTO DEBIAN (.deb)
# ==============================================================================
set -euo pipefail

PACKAGE_NAME="scannerpan"
VERSION="1.0.0"
ARCH="amd64"
DEB_FILENAME="${PACKAGE_NAME}_${VERSION}_${ARCH}.deb"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_ROOT="${SCRIPT_DIR}/build_pkg"

echo "🚀 [ScannerPan] Avvio creazione pacchetto Debian: ${DEB_FILENAME}..."

# 1. Pulizia ambiente di build precedente
rm -rf "${BUILD_ROOT}"
rm -f "${SCRIPT_DIR}/${DEB_FILENAME}"

# 2. Creazione struttura directory FHS
echo "📁 Creazione albero filesystem Debian..."
mkdir -p "${BUILD_ROOT}/DEBIAN"
mkdir -p "${BUILD_ROOT}/usr/bin"
mkdir -p "${BUILD_ROOT}/usr/lib/scannerpan/scannerpan"
mkdir -p "${BUILD_ROOT}/usr/share/applications"
mkdir -p "${BUILD_ROOT}/usr/share/icons/hicolor/scalable/apps"
mkdir -p "${BUILD_ROOT}/usr/share/doc/scannerpan"

# 3. Creazione file DEBIAN/control
echo "📝 Generazione DEBIAN/control..."
cat << 'EOF' > "${BUILD_ROOT}/DEBIAN/control"
Package: scannerpan
Version: 1.0.0
Section: graphics
Priority: optional
Architecture: amd64
Maintainer: MrPan <marcopanista@gmail.com>
Depends: python3, python3-pyqt6, python3-pil, python3-opencv, python3-docx, python3-odf, sane-utils, tesseract-ocr, poppler-utils, imagemagick
Recommends: sane-airscan, ipp-usb
Description: Modern Linux and KDE Scanning Application
 ScannerPan provides an intuitive, high-performance scanning interface
 designed for KDE Plasma and Linux. It features Brother MFC-1910W support,
 SANE / airscan integration, automatic multi-subject cropping (photos, receipts),
 perspective correction and OCR export to PDF, Word and OpenDocument.
EOF

# 4. Creazione wrapper /usr/bin/scannerpan
echo "⚙️  Creazione wrapper eseguibile /usr/bin/scannerpan..."
cat << 'EOF' > "${BUILD_ROOT}/usr/bin/scannerpan"
#!/bin/sh
export PYTHONPATH="/usr/lib/scannerpan:${PYTHONPATH}"
exec /usr/bin/python3 -m scannerpan.app "$@"
EOF
chmod 755 "${BUILD_ROOT}/usr/bin/scannerpan"

# 5. Copia codice sorgente Python
echo "📦 Copia moduli Python in /usr/lib/scannerpan/scannerpan..."
cp -r "${SCRIPT_DIR}/scannerpan/"* "${BUILD_ROOT}/usr/lib/scannerpan/scannerpan/"

# Rimuovi cache compilate residue
find "${BUILD_ROOT}/usr/lib/scannerpan" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "${BUILD_ROOT}/usr/lib/scannerpan" -type f -name "*.pyc" -delete 2>/dev/null || true

# 6. Copia desktop file e icona SVG
echo "🎨 Copia desktop launcher e icone KDE..."
cp "${SCRIPT_DIR}/resources/scannerpan.desktop" "${BUILD_ROOT}/usr/share/applications/scannerpan.desktop"
chmod 644 "${BUILD_ROOT}/usr/share/applications/scannerpan.desktop"

cp "${SCRIPT_DIR}/resources/scannerpan.svg" "${BUILD_ROOT}/usr/share/icons/hicolor/scalable/apps/scannerpan.svg"
chmod 644 "${BUILD_ROOT}/usr/share/icons/hicolor/scalable/apps/scannerpan.svg"

# 7. Documentazione / copyright
cat << 'EOF' > "${BUILD_ROOT}/usr/share/doc/scannerpan/copyright"
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: ScannerPan
Source: https://gitlab.com/mrpan-group/MrPan-project

Files: *
Copyright: 2026 MrPan <marcopanista@gmail.com>
License: GPL-3.0+
EOF

# 8. Compilazione pacchetto deb
echo "🔨 Compilazione pacchetto con dpkg-deb..."
dpkg-deb --build --root-owner-group "${BUILD_ROOT}" "${SCRIPT_DIR}/${DEB_FILENAME}"

# 8b. Copia pacchetto in uploads/ per download immediato da repository
mkdir -p "${SCRIPT_DIR}/uploads"
cp "${SCRIPT_DIR}/${DEB_FILENAME}" "${SCRIPT_DIR}/uploads/${DEB_FILENAME}"

# 9. Pulizia build temporanea
rm -rf "${BUILD_ROOT}"

echo "✅ Pacchetto creato con successo: ${SCRIPT_DIR}/${DEB_FILENAME}"
echo "📊 Informazioni pacchetto generato:"
dpkg-deb -I "${SCRIPT_DIR}/${DEB_FILENAME}"
echo "📂 Contenuto del pacchetto:"
dpkg-deb -c "${SCRIPT_DIR}/${DEB_FILENAME}"
