"""KaizenReader Native macOS Application Shell.

Leverages Apple Silicon native Cocoa and WebKit frameworks via PyObjC.
Consumes <40MB RAM (rejecting Electron's 1.5GB bloat) while providing
a true macOS desktop window with Dock icon, Apple menu bar, and shortcuts.
"""
import sys
import time
import socket
import threading
from pathlib import Path
from urllib.request import urlopen

# Ensure root directory is on Python path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import Cocoa
from Cocoa import (
    NSApplication, NSApp, NSWindow, NSBackingStoreBuffered,
    NSWindowStyleMaskTitled, NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable, NSWindowStyleMaskResizable,
    NSRect, NSPoint, NSSize, NSMenu, NSMenuItem, NSObject,
    NSApplicationActivationPolicyRegular
)
import WebKit
from WebKit import WKWebView, WKWebViewConfiguration

from src.config import DEFAULT_PORT, DEFAULT_HOST

def is_server_ready(port: int = DEFAULT_PORT) -> bool:
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/status", timeout=0.8) as res:
            return res.status == 200
    except Exception:
        return False

def start_backend_server():
    """Start uvicorn server in a background thread if not already running."""
    import uvicorn
    from src.server.app import app
    uvicorn.run(app, host=DEFAULT_HOST, port=DEFAULT_PORT, log_level="warning")

class NavigationDelegate(NSObject):
    def webView_didStartProvisionalNavigation_(self, webview, navigation):
        pass

    def webView_didFinishNavigation_(self, webview, navigation):
        print(f"[AppShell] KaizenReader interface loaded successfully at http://127.0.0.1:{DEFAULT_PORT}")

    def webView_didFailProvisionalNavigation_withError_(self, webview, navigation, error):
        print(f"[AppShell] Initial connection pending ({error.localizedDescription()}), retrying...")
        # Auto-retry loading in 0.5s
        Cocoa.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.5, self, "retryLoad:", webview, False
        )

    def retryLoad_(self, timer):
        webview = timer.userInfo()
        url = Cocoa.NSURL.URLWithString_(f"http://127.0.0.1:{DEFAULT_PORT}")
        request = Cocoa.NSURLRequest.requestWithURL_(url)
        webview.loadRequest_(request)

class AppDelegate(NSObject):
    def applicationDidFinishLaunching_(self, notification):
        self.window.center()
        self.window.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)

    def applicationShouldTerminateAfterLastWindowClosed_(self, sender):
        return True

def create_menu_bar(window):
    menubar = NSMenu.alloc().init()
    app_menu_item = NSMenuItem.alloc().init()
    menubar.addItem_(app_menu_item)

    app_menu = NSMenu.alloc().init()
    quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Quit KaizenReader", "terminate:", "q"
    )
    app_menu.addItem_(quit_item)
    app_menu_item.setSubmenu_(app_menu)

    # Edit Menu (Standard macOS shortcuts)
    edit_menu_item = NSMenuItem.alloc().init()
    menubar.addItem_(edit_menu_item)
    edit_menu = NSMenu.alloc().initWithTitle_("Edit")
    edit_menu.addItemWithTitle_action_keyEquivalent_("Undo", "undo:", "z")
    edit_menu.addItemWithTitle_action_keyEquivalent_("Redo", "redo:", "Z")
    edit_menu.addItem_(NSMenuItem.separatorItem())
    edit_menu.addItemWithTitle_action_keyEquivalent_("Cut", "cut:", "x")
    edit_menu.addItemWithTitle_action_keyEquivalent_("Copy", "copy:", "c")
    edit_menu.addItemWithTitle_action_keyEquivalent_("Paste", "paste:", "v")
    edit_menu.addItemWithTitle_action_keyEquivalent_("Select All", "selectAll:", "a")
    edit_menu_item.setSubmenu_(edit_menu)

    # View Menu with Reload
    view_menu_item = NSMenuItem.alloc().init()
    menubar.addItem_(view_menu_item)
    view_menu = NSMenu.alloc().initWithTitle_("View")
    reload_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Reload Reader", "reload:", "r"
    )
    reload_item.setTarget_(window.contentView())
    view_menu.addItem_(reload_item)
    view_menu_item.setSubmenu_(view_menu)

    # Window Menu
    window_menu_item = NSMenuItem.alloc().init()
    menubar.addItem_(window_menu_item)
    window_menu = NSMenu.alloc().initWithTitle_("Window")
    window_menu.addItemWithTitle_action_keyEquivalent_("Minimize", "performMiniaturize:", "m")
    window_menu.addItemWithTitle_action_keyEquivalent_("Zoom", "performZoom:", "")
    window_menu_item.setSubmenu_(window_menu)

    NSApp.setMainMenu_(menubar)

def launch_native_window():
    # 1. Start backend server if not running
    if not is_server_ready(DEFAULT_PORT):
        print("[AppShell] Starting KaizenReader core engine in background...")
        t = threading.Thread(target=start_backend_server, daemon=True)
        t.start()

        # Wait until server is fully responding
        for _ in range(80):
            if is_server_ready(DEFAULT_PORT):
                break
            time.sleep(0.1)

    # 2. Initialize NSApplication
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)

    # 3. Create Desktop Window
    frame = NSRect(NSPoint(150, 150), NSSize(1150, 820))
    style_mask = (
        NSWindowStyleMaskTitled |
        NSWindowStyleMaskClosable |
        NSWindowStyleMaskMiniaturizable |
        NSWindowStyleMaskResizable
    )
    window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        frame, style_mask, NSBackingStoreBuffered, False
    )
    window.setTitle_("KaizenReader — Studio TTS for Apple Silicon M1")
    window.setMinSize_(NSSize(800, 600))

    create_menu_bar(window)

    # 4. Create WebKit View & Navigation Delegate
    config = WKWebViewConfiguration.alloc().init()
    config.preferences().setValue_forKey_(True, "developerExtrasEnabled")

    webview = WKWebView.alloc().initWithFrame_configuration_(frame, config)
    nav_delegate = NavigationDelegate.alloc().init()
    webview.setNavigationDelegate_(nav_delegate)

    window.setContentView_(webview)

    # Load local URL
    url = Cocoa.NSURL.URLWithString_(f"http://127.0.0.1:{DEFAULT_PORT}")
    request = Cocoa.NSURLRequest.requestWithURL_(url)
    webview.loadRequest_(request)

    # 5. Set App Delegate
    delegate = AppDelegate.alloc().init()
    delegate.window = window
    app.setDelegate_(delegate)

    app.run()

if __name__ == "__main__":
    launch_native_window()
