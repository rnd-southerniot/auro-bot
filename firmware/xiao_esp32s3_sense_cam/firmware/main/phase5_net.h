/*
 * phase5_net.h — Phase 5.1 Wi-Fi STA bring-up.
 *
 * Brings up nvs_flash, esp_netif, the default event loop, the Wi-Fi
 * driver in STA mode, and blocks until either an IPv4 address is
 * obtained or CONFIG_WIFI_CONNECT_TIMEOUT_MS elapses.
 *
 * One-shot. Re-calling after a successful start is a programming error.
 */

#pragma once

#include "esp_err.h"

/* Bring up Wi-Fi STA and block until IP is assigned.
 *
 * Returns:
 *   ESP_OK              — connected, IP logged
 *   ESP_ERR_INVALID_ARG — CONFIG_WIFI_SSID empty (see Kconfig)
 *   ESP_ERR_TIMEOUT     — no IP within CONFIG_WIFI_CONNECT_TIMEOUT_MS
 *   other               — propagated from esp_wifi_*
 */
esp_err_t phase5_net_start_blocking(void);
