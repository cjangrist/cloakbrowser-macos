FROM upstream-source

ARG UPSTREAM_SHA=unknown

LABEL org.opencontainers.image.source="https://github.com/cjangrist/cloakbrowser-macos" \
      org.opencontainers.image.url="https://github.com/cjangrist/cloakbrowser-macos/pkgs/container/cloakbrowser-macos" \
      org.opencontainers.image.description="Source-built CloakBrowser with a persistent headed macOS CDP profile" \
      net.angrist.cloakbrowser.upstream.repository="https://github.com/CloakHQ/CloakBrowser" \
      net.angrist.cloakbrowser.upstream.revision="${UPSTREAM_SHA}"

COPY --chmod=0755 bin/default-cloakserve /usr/local/bin/default-cloakserve

ENV CLOAKBROWSER_FETCH_WIDEVINE=1 \
    CLOAKBROWSER_DISPLAY_WIDTH=1440 \
    CLOAKBROWSER_DISPLAY_HEIGHT=900 \
    CLOAKSERVE_PORT=9222 \
    CLOAKSERVE_HEADLESS=false \
    CLOAKSERVE_DATA_DIR=/root/.cloakbrowser/profiles/macos \
    CLOAKSERVE_IDLE_TIMEOUT=0 \
    CLOAKSERVE_PRESERVE_PROFILES=true \
    CLOAKBROWSER_START_MAXIMIZED=true \
    CLOAKBROWSER_FINGERPRINT=18929 \
    CLOAKBROWSER_FINGERPRINT_PLATFORM=macos \
    CLOAKBROWSER_FINGERPRINT_BRAND=Chrome \
    CLOAKBROWSER_FINGERPRINT_TIMEZONE=America/New_York \
    CLOAKBROWSER_FINGERPRINT_LOCALE=en-US \
    CLOAKBROWSER_FINGERPRINT_NOISE=false \
    CLOAKBROWSER_FINGERPRINT_STORAGE_QUOTA=5000 \
    CLOAKBROWSER_FINGERPRINT_ALLOW_3P_COOKIES=true

EXPOSE 9222
VOLUME ["/root/.cloakbrowser"]
STOPSIGNAL SIGTERM

HEALTHCHECK --interval=15s --timeout=10s --start-period=120s --retries=20 \
  CMD curl --fail --silent "http://127.0.0.1:${CLOAKSERVE_PORT}/json/version" >/dev/null || exit 1

CMD ["default-cloakserve"]
