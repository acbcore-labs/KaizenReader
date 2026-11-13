#!/usr/bin/env bash
# KaizenReader Native macOS App Installer
# Installs KaizenReader.app into ~/Applications for instant Spotlight and Raycast indexing.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_APP="$HOME/Applications/KaizenReader.app"

echo "=================================================="
echo "Installing KaizenReader to ~/Applications..."
echo "=================================================="

# Ensure directories exist
mkdir -p "$HOME/Applications"
mkdir -p "$TARGET_APP/Contents/MacOS"
mkdir -p "$TARGET_APP/Contents/Resources"

# 1. Write Info.plist
cat << 'EOF' > "$TARGET_APP/Contents/Info.plist"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>en</string>
    <key>CFBundleDisplayName</key>
    <string>KaizenReader</string>
    <key>CFBundleExecutable</key>
    <string>KaizenReader</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundleIdentifier</key>
    <string>com.kaizentrading.reader</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>KaizenReader</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSMinimumSystemVersion</key>
    <string>12.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSAppTransportSecurity</key>
    <dict>
        <key>NSAllowsLocalNetworking</key>
        <true/>
        <key>NSAllowsArbitraryLoads</key>
        <true/>
    </dict>
</dict>
</plist>
EOF

# 2. Write PkgInfo
echo -n "APPL????" > "$TARGET_APP/Contents/PkgInfo"

# 3. Copy Icon
if [ -f "$SCRIPT_DIR/sample_books/AppIcon.icns" ]; then
    cp "$SCRIPT_DIR/sample_books/AppIcon.icns" "$TARGET_APP/Contents/Resources/AppIcon.icns"
fi

# 4. Create MacOS Launcher Script
cat << EOF > "$TARGET_APP/Contents/MacOS/KaizenReader"
#!/usr/bin/env bash
REPO_DIR="$SCRIPT_DIR"
cd "\$REPO_DIR" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:\$PATH"
exec "\$REPO_DIR/.venv/bin/python" "\$REPO_DIR/src/main.py" "\$@"
EOF

chmod +x "$TARGET_APP/Contents/MacOS/KaizenReader"

# 5. Register with macOS LaunchServices so Spotlight indexes it immediately
echo "Registering with macOS LaunchServices & Spotlight..."
LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
if [ -f "$LSREGISTER" ]; then
    "$LSREGISTER" -f "$TARGET_APP"
fi

touch "$TARGET_APP"

echo ""
echo "Installation complete!"
echo "KaizenReader is now installed in: $TARGET_APP"
echo "You can now press Cmd+Space and type 'KaizenReader' to launch it anytime!"
