#!/usr/bin/env bash
# Verify environment variables map to exact CloakServe arguments without shell re-evaluation.

set -Eeuo pipefail

main() {
  local launcher_output

  launcher_output="$(
    CLOAKSERVE_BINARY=/bin/echo \
    CLOAKSERVE_PORT=9333 \
    CLOAKSERVE_HEADLESS=true \
    CLOAKSERVE_DATA_DIR='/tmp/profile with spaces' \
    CLOAKSERVE_IDLE_TIMEOUT=42 \
    CLOAKSERVE_PRESERVE_PROFILES=false \
    CLOAKBROWSER_START_MAXIMIZED=false \
    CLOAKBROWSER_FINGERPRINT=77777 \
    CLOAKBROWSER_FINGERPRINT_PLATFORM=macos \
    CLOAKBROWSER_FINGERPRINT_BRAND=Chrome \
    CLOAKBROWSER_FINGERPRINT_TIMEZONE=America/Los_Angeles \
    CLOAKBROWSER_FINGERPRINT_LOCALE=en-US \
    CLOAKBROWSER_FINGERPRINT_NOISE=false \
    CLOAKBROWSER_FINGERPRINT_STORAGE_QUOTA=6000 \
    CLOAKBROWSER_FINGERPRINT_ALLOW_3P_COOKIES=false \
    bin/default-cloakserve
  )"

  [[ "${launcher_output}" == *"--port=9333"* ]]
  [[ "${launcher_output}" == *"--data-dir=/tmp/profile with spaces"* ]]
  [[ "${launcher_output}" == *"--idle-timeout=42"* ]]
  [[ "${launcher_output}" == *"--preserve-profiles=false"* ]]
  [[ "${launcher_output}" == *"--fingerprint=77777"* ]]
  [[ "${launcher_output}" == *"--fingerprint-timezone=America/Los_Angeles"* ]]
  [[ "${launcher_output}" != *"--headless=false"* ]]
  [[ "${launcher_output}" != *"--fingerprint-allow-3p-cookies"* ]]
  [[ "${launcher_output}" != *"--start-maximized"* ]]

  if CLOAKSERVE_HEADLESS=maybe CLOAKSERVE_BINARY=/usr/bin/true bin/default-cloakserve; then
    printf 'Invalid boolean unexpectedly succeeded\n' >&2
    return 1
  fi
}

main "$@"
