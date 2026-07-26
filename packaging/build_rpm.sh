#!/usr/bin/env bash
# Build the .rpm from an existing PyInstaller onedir bundle.
# Usage: packaging/build_rpm.sh [version]   (default 0.1.0)
# Prereq: .venv/bin/pyinstaller packaging/medical-redactor.spec --noconfirm
set -euo pipefail

cd "$(dirname "$0")/.."
VERSION="${1:-0.1.0}"
BUNDLE="$PWD/dist/medical-redactor"
[ -x "$BUNDLE/medical-redactor" ] || {
    echo "No bundle at $BUNDLE — run pyinstaller first." >&2
    exit 1
}

TOP="$PWD/build/rpm"
mkdir -p "$TOP"/{BUILD,RPMS,SPECS,SRPMS}

rpmbuild -bb packaging/medical-redactor.rpmspec \
    --define "_topdir $TOP" \
    --define "_bundle_dir $BUNDLE" \
    --define "_pkgsrc_dir $PWD/packaging" \
    --define "version $VERSION"

find "$TOP/RPMS" -name '*.rpm' -exec cp -v {} dist/ \;
