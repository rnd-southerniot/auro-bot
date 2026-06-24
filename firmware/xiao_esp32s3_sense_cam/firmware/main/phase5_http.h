/*
 * phase5_http.h — Phase 5.2 HTTP server.
 *
 * Brings up esp_http_server on :80 and registers handlers:
 *   GET /          → tiny HTML page with <img src="/stream">
 *   GET /stream    → multipart/x-mixed-replace MJPEG (live)
 *   GET /snapshot  → single image/jpeg
 *
 * Pulls frames from phase5_cam_pump.
 */

#pragma once

#include "esp_err.h"

esp_err_t phase5_http_start(void);
