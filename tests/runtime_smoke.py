#!/usr/bin/env python3
"""Validate the live CDP browser fingerprint, media support, and profile persistence."""

from __future__ import annotations

import argparse
import json
import logging
import secrets
import sys
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

LOGGER = logging.getLogger("cloakbrowser-runtime-smoke")
COLOR_GREEN = "\033[32m"
COLOR_BLUE = "\033[34m"
COLOR_RESET = "\033[0m"
EXPECTED_QUOTA_BYTES = 5000 * 1024 * 1024
STABLE_SIGNAL_KEYS = (
    "user_agent",
    "platform",
    "client_hints",
    "hardware_concurrency",
    "device_memory",
    "screen",
    "viewport",
    "timezone",
    "language",
    "languages",
    "plugins",
    "webgl_vendor",
    "webgl_renderer",
    "canvas_hash",
    "audio_hash",
    "font_metrics",
)
MACOS_FONT_FAMILIES = (
    "Apple Color Emoji",
    "Arial",
    "Arial Narrow",
    "Arial Unicode MS",
    "Comic Sans MS",
    "Courier",
    "Courier New",
    "Georgia",
    "Gill Sans",
    "Helvetica",
    "Helvetica Neue",
    "Impact",
    "Menlo",
    "Microsoft Sans Serif",
    "Monaco",
    "Tahoma",
    "Times New Roman",
    "Trebuchet MS",
    "Webdings",
    "Wingdings",
    "Avenir",
    "Avenir Next",
    "Avenir Next Condensed",
    "Geneva",
    "Lucida Grande",
    "Palatino",
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9222")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--phase", choices=("initialize", "verify"), required=True)
    parser.add_argument("--require-blink-system-font", action="store_true")
    return parser.parse_args()


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format=f"{COLOR_BLUE}%(asctime)s{COLOR_RESET} %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )


def browser_probe_script() -> str:
    return r"""
async () => {
  const canvas = document.createElement('canvas');
  canvas.width = 320;
  canvas.height = 80;
  const context2d = canvas.getContext('2d');
  context2d.font = '24px Arial';
  context2d.fillStyle = '#f60';
  context2d.fillRect(8, 8, 96, 48);
  context2d.fillStyle = '#069';
  context2d.fillText('CloakBrowser 18929', 12, 42);
  const canvasBytes = new TextEncoder().encode(canvas.toDataURL());
  const canvasDigest = await crypto.subtle.digest('SHA-256', canvasBytes);

  const webglCanvas = document.createElement('canvas');
  const gl = webglCanvas.getContext('webgl');
  const extension = gl && gl.getExtension('WEBGL_debug_renderer_info');

  const audioContext = new OfflineAudioContext(1, 4096, 44100);
  const oscillator = audioContext.createOscillator();
  const compressor = audioContext.createDynamicsCompressor();
  oscillator.type = 'triangle';
  oscillator.frequency.value = 440;
  oscillator.connect(compressor);
  compressor.connect(audioContext.destination);
  oscillator.start(0);
  const rendered = await audioContext.startRendering();
  const samples = rendered.getChannelData(0);
  const audioDigest = await crypto.subtle.digest('SHA-256', samples.buffer);

  let widevineSupported = false;
  let widevineError = null;
  try {
    await navigator.requestMediaKeySystemAccess('com.widevine.alpha', [{
      initDataTypes: ['cenc'],
      audioCapabilities: [{contentType: 'audio/mp4; codecs="mp4a.40.2"'}],
      videoCapabilities: [{contentType: 'video/mp4; codecs="avc1.42E01E"'}]
    }]);
    widevineSupported = true;
  } catch (error) {
    widevineError = String(error);
  }

  const highEntropy = navigator.userAgentData
    ? await navigator.userAgentData.getHighEntropyValues([
        'architecture', 'bitness', 'model', 'platformVersion', 'uaFullVersion'
      ])
    : null;
  const storage = await navigator.storage.estimate();
  const fontFamilies = [
    'Apple Color Emoji', 'Arial', 'Arial Narrow', 'Arial Unicode MS',
    'Comic Sans MS', 'Courier', 'Courier New', 'Georgia', 'Gill Sans',
    'Helvetica', 'Helvetica Neue', 'Impact', 'Menlo', 'Microsoft Sans Serif',
    'Monaco', 'Tahoma', 'Times New Roman', 'Trebuchet MS', 'Webdings',
    'Wingdings', 'Avenir', 'Avenir Next', 'Avenir Next Condensed', 'Geneva',
    'Lucida Grande', 'Palatino', 'BlinkMacSystemFont'
  ];
  const fontCanvas = document.createElement('canvas');
  const fontContext = fontCanvas.getContext('2d');
  const fontText = 'CloakBrowser WMWM iii 0123456789 🌎🚀';
  const measureFont = family => {
    const genericFamilies = ['serif', 'sans-serif', 'monospace'];
    const metricKeys = ['width', 'actualBoundingBoxAscent', 'actualBoundingBoxDescent'];
    const measurements = genericFamilies.map(genericFamily => {
      fontContext.font = `32px "__CloakMissingFont__", ${genericFamily}`;
      const fallback = fontContext.measureText(fontText);
      fontContext.font = `32px "${family}", "__CloakMissingFont__", ${genericFamily}`;
      const measured = fontContext.measureText(fontText);
      return {
        genericFamily,
        fallback: Object.fromEntries(metricKeys.map(key => [key, fallback[key]])),
        measured: Object.fromEntries(metricKeys.map(key => [key, measured[key]])),
        differs: metricKeys.some(key => Math.abs(measured[key] - fallback[key]) > 0.01)
      };
    });
    return {
      measurements,
      differs_from_fallback: measurements.some(measurement => measurement.differs)
    };
  };
  const fontMetrics = Object.fromEntries(fontFamilies.map(family => [family, measureFont(family)]));
  const hexadecimal = value => Array.from(new Uint8Array(value))
    .map(byte => byte.toString(16).padStart(2, '0')).join('');

  return {
    user_agent: navigator.userAgent,
    platform: navigator.platform,
    client_hints: highEntropy,
    webdriver: navigator.webdriver,
    hardware_concurrency: navigator.hardwareConcurrency,
    device_memory: navigator.deviceMemory,
    screen: {
      width: screen.width,
      height: screen.height,
      availWidth: screen.availWidth,
      availHeight: screen.availHeight,
      colorDepth: screen.colorDepth,
      pixelDepth: screen.pixelDepth
    },
    viewport: {innerWidth, innerHeight, outerWidth, outerHeight, devicePixelRatio},
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    language: navigator.language,
    languages: navigator.languages,
    plugins: Array.from(navigator.plugins, plugin => plugin.name),
    webgl_vendor: extension ? gl.getParameter(extension.UNMASKED_VENDOR_WEBGL) : null,
    webgl_renderer: extension ? gl.getParameter(extension.UNMASKED_RENDERER_WEBGL) : null,
    canvas_hash: hexadecimal(canvasDigest),
    audio_hash: hexadecimal(audioDigest),
    font_metrics: fontMetrics,
    storage_quota: storage.quota,
    widevine_supported: widevineSupported,
    widevine_error: widevineError
  };
}
"""


def capture_signals(cdp_url: str, marker: str, initialize: bool) -> dict[str, Any]:
    LOGGER.info("Connecting to CDP endpoint %s", cdp_url)
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(cdp_url)
        context = browser.contexts[0]
        page = context.new_page()
        response = page.goto("https://example.com", wait_until="domcontentloaded", timeout=30000)
        if response is None or not response.ok:
            raise AssertionError("example.com navigation did not return a successful response")
        if initialize:
            page.evaluate("value => localStorage.setItem('cloakbrowserPersistence', value)", marker)
            page.evaluate(
                "value => { document.cookie = `cloakbrowserPersistence=${value}; Max-Age=86400; Path=/; SameSite=Lax; Secure`; }",
                marker,
            )
        signals = page.evaluate(browser_probe_script())
        signals["local_storage_marker"] = page.evaluate("localStorage.getItem('cloakbrowserPersistence')")
        cookies = context.cookies("https://example.com")
        signals["cookie_marker"] = next(
            (cookie["value"] for cookie in cookies if cookie["name"] == "cloakbrowserPersistence"),
            None,
        )
        signals["cookie_metadata"] = [
            {key: cookie[key] for key in ("name", "domain", "path", "expires", "httpOnly", "secure", "sameSite")}
            for cookie in cookies
            if cookie["name"] == "cloakbrowserPersistence"
        ]
        page.close()
        browser.close()
    LOGGER.info("Captured %d runtime signals", len(signals))
    return signals


def validate_profile(signals: dict[str, Any], require_blink_system_font: bool) -> None:
    missing_fonts = [
        family
        for family in MACOS_FONT_FAMILIES
        if family != "Apple Color Emoji"
        if not signals["font_metrics"].get(family, {}).get("differs_from_fallback", False)
    ]
    if require_blink_system_font and not signals["font_metrics"].get(
        "BlinkMacSystemFont", {}
    ).get("differs_from_fallback", False):
        missing_fonts.append("BlinkMacSystemFont")
    assertions = {
        "macOS user agent": "Macintosh" in signals["user_agent"],
        "Chrome brand": "Chrome/" in signals["user_agent"],
        "macOS platform": signals["platform"] == "MacIntel",
        "webdriver disabled": signals["webdriver"] is False,
        "Apple GPU vendor": "Apple" in (signals["webgl_vendor"] or ""),
        "non-empty GPU renderer": bool(signals["webgl_renderer"]),
        "hardware concurrency": signals["hardware_concurrency"] >= 2,
        "device memory": signals["device_memory"] >= 2,
        "screen coherence": signals["screen"]["width"] >= signals["viewport"]["innerWidth"],
        "window coherence": signals["viewport"]["outerWidth"] >= signals["viewport"]["innerWidth"],
        "timezone": signals["timezone"] == "America/New_York",
        "locale": signals["language"] == "en-US",
        "plugins": len(signals["plugins"]) >= 3,
        "storage quota": abs(signals["storage_quota"] - EXPECTED_QUOTA_BYTES) < 16 * 1024 * 1024,
        "Widevine EME": signals["widevine_supported"] is True,
        "macOS font metrics": not missing_fonts,
    }
    failures = [name for name, passed in assertions.items() if not passed]
    for name, passed in assertions.items():
        LOGGER.info("%s%s%s: %s", COLOR_GREEN if passed else "\033[31m", name, COLOR_RESET, passed)
    if failures:
        details = f"; missing font metrics: {', '.join(missing_fonts)}" if missing_fonts else ""
        raise AssertionError(f"runtime checks failed: {', '.join(failures)}{details}")


def validate_persistence(signals: dict[str, Any], baseline: dict[str, Any]) -> None:
    if signals["local_storage_marker"] != baseline["local_storage_marker"]:
        raise AssertionError("localStorage marker did not survive container recreation")
    if signals["cookie_marker"] != baseline["cookie_marker"]:
        raise AssertionError("cookie marker did not survive container recreation")
    changed = [key for key in STABLE_SIGNAL_KEYS if signals[key] != baseline[key]]
    if changed:
        raise AssertionError(f"fingerprint signals changed after recreation: {', '.join(changed)}")
    LOGGER.info("Profile state and %d fingerprint signals survived recreation", len(STABLE_SIGNAL_KEYS))


def main() -> int:
    configure_logging()
    arguments = parse_arguments()
    baseline = json.loads(arguments.baseline.read_text()) if arguments.baseline else None
    marker = baseline["local_storage_marker"] if baseline else secrets.token_hex(16)
    signals = capture_signals(arguments.cdp_url, marker, arguments.phase == "initialize")
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(signals, indent=2, sort_keys=True) + "\n")
    LOGGER.info("Wrote sanitized results to %s", arguments.output)
    validate_profile(signals, arguments.require_blink_system_font)
    if arguments.phase == "verify":
        if baseline is None:
            raise ValueError("--baseline is required for verify phase")
        validate_persistence(signals, baseline)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        LOGGER.exception("Runtime smoke test failed")
        sys.exit(1)
