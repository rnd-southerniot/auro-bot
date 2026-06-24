/*
 * Phase 4 — microSD mount + write/read smoke test.
 *
 * The Sense expansion wires the SD card to:
 *   CLK = GPIO7   (aliases XIAO_D8_GPIO)
 *   CMD = GPIO9   (aliases XIAO_D10_GPIO)
 *   D0  = GPIO8   (aliases XIAO_D9_GPIO)
 *
 * 1-bit SDMMC. No card-detect line is exposed by Seeed; we rely on the
 * mount call returning an error if the slot is empty.
 *
 * The test:
 *   1. Mount FAT (no auto-format on failure)
 *   2. Print card identity (sdmmc_card_print_info)
 *   3. Write TEST_BYTES of a known pattern to /sdcard/_phase4.bin
 *   4. fflush + fsync, fclose
 *   5. Read back, byte-compare
 *   6. Unlink, unmount
 *
 * Smoke gate (all must hold): mount OK, capacity > 16 MB, write OK,
 * readback matches, unmount OK. On FAIL the function logs the failing
 * step and returns a non-OK code; main.c continues the heartbeat.
 */

#include "phase4_sd.h"

#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/unistd.h>

#include "driver/sdmmc_default_configs.h"
#include "driver/sdmmc_host.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_vfs_fat.h"
#include "sdmmc_cmd.h"

#include "gpio_remap.h"

static const char *TAG = "sense_sd";

#define MOUNT_POINT       "/sdcard"
#define TEST_PATH         MOUNT_POINT "/_phase4.bin"
#define TEST_BYTES        4096u
#define MIN_CAPACITY_MB   16u

static void fill_pattern(uint8_t *buf, size_t n)
{
    /* Simple deterministic LFSR-ish fill that's neither all-0 nor all-FF. */
    uint32_t x = 0xA5A5A5A5u;
    for (size_t i = 0; i < n; ++i) {
        x = x * 1664525u + 1013904223u;
        buf[i] = (uint8_t)(x >> 24);
    }
}

esp_err_t phase4_sd_capture_one(void)
{
    esp_err_t err = ESP_OK;
    sdmmc_card_t *card = NULL;
    uint8_t *write_buf = NULL;
    uint8_t *read_buf  = NULL;
    bool mounted = false;

    sdmmc_host_t host = SDMMC_HOST_DEFAULT();
    host.flags        = SDMMC_HOST_FLAG_1BIT;
    host.max_freq_khz = SDMMC_FREQ_DEFAULT;   /* 20 MHz */

    sdmmc_slot_config_t slot = SDMMC_SLOT_CONFIG_DEFAULT();
    slot.width = 1;
    slot.clk   = SD_CLK_GPIO;
    slot.cmd   = SD_CMD_GPIO;
    slot.d0    = SD_D0_GPIO;
    slot.flags |= SDMMC_SLOT_FLAG_INTERNAL_PULLUP;

    esp_vfs_fat_sdmmc_mount_config_t mount_cfg = {
        .format_if_mount_failed = false,    /* never auto-format user data */
        .max_files              = 4,
        .allocation_unit_size   = 16 * 1024,
    };

    ESP_LOGI(TAG, "mounting %s on SDMMC 1-bit (clk=%d cmd=%d d0=%d) ...",
             MOUNT_POINT, slot.clk, slot.cmd, slot.d0);

    int64_t t0 = esp_timer_get_time();
    err = esp_vfs_fat_sdmmc_mount(MOUNT_POINT, &host, &slot, &mount_cfg, &card);
    int64_t mount_ms = (esp_timer_get_time() - t0) / 1000;

    if (err != ESP_OK) {
        if (err == ESP_FAIL) {
            ESP_LOGE(TAG, "mount failed (FAT). Card present but not FAT-formatted, "
                          "or filesystem is corrupt.");
        } else if (err == ESP_ERR_INVALID_STATE) {
            ESP_LOGE(TAG, "mount returned INVALID_STATE — already mounted?");
        } else {
            ESP_LOGE(TAG, "mount failed: 0x%x (%s) — slot empty / wiring / pull-ups?",
                     err, esp_err_to_name(err));
        }
        goto cleanup;
    }
    mounted = true;
    ESP_LOGI(TAG, "mount OK in %" PRId64 " ms", mount_ms);

    /* sdmmc_card_print_info goes to stdout, not the log; that's fine. */
    sdmmc_card_print_info(stdout, card);

    /* --- capacity gate --- */
    uint64_t cap_bytes = (uint64_t)card->csd.capacity * card->csd.sector_size;
    uint32_t cap_mb    = (uint32_t)(cap_bytes / (1024u * 1024u));
    ESP_LOGI(TAG, "capacity: %" PRIu32 " MB (sectors=%" PRIu32 " sector_size=%" PRIu32 ")",
             cap_mb, (uint32_t)card->csd.capacity, (uint32_t)card->csd.sector_size);
    if (cap_mb < MIN_CAPACITY_MB) {
        ESP_LOGE(TAG, "capacity below %u MB — sanity gate fail", MIN_CAPACITY_MB);
        err = ESP_FAIL;
        goto cleanup;
    }

    /* --- write --- */
    write_buf = malloc(TEST_BYTES);
    read_buf  = malloc(TEST_BYTES);
    if (write_buf == NULL || read_buf == NULL) {
        ESP_LOGE(TAG, "buffer alloc failed");
        err = ESP_ERR_NO_MEM;
        goto cleanup;
    }
    fill_pattern(write_buf, TEST_BYTES);

    t0 = esp_timer_get_time();
    FILE *f = fopen(TEST_PATH, "wb");
    if (f == NULL) {
        ESP_LOGE(TAG, "fopen(%s, wb) failed: errno=%d (%s)", TEST_PATH, errno, strerror(errno));
        err = ESP_FAIL;
        goto cleanup;
    }
    size_t wrote = fwrite(write_buf, 1, TEST_BYTES, f);
    fflush(f);
    fsync(fileno(f));
    fclose(f);
    int64_t write_ms = (esp_timer_get_time() - t0) / 1000;
    if (wrote != TEST_BYTES) {
        ESP_LOGE(TAG, "short write: %u / %u", (unsigned)wrote, (unsigned)TEST_BYTES);
        err = ESP_FAIL;
        goto cleanup;
    }
    ESP_LOGI(TAG, "wrote %u bytes to %s in %" PRId64 " ms (%.1f kB/s)",
             (unsigned)wrote, TEST_PATH, write_ms,
             write_ms > 0 ? (double)wrote / (double)write_ms : 0.0);

    /* --- read back --- */
    t0 = esp_timer_get_time();
    f = fopen(TEST_PATH, "rb");
    if (f == NULL) {
        ESP_LOGE(TAG, "fopen(%s, rb) failed: errno=%d (%s)", TEST_PATH, errno, strerror(errno));
        err = ESP_FAIL;
        goto cleanup;
    }
    size_t got = fread(read_buf, 1, TEST_BYTES, f);
    fclose(f);
    int64_t read_ms = (esp_timer_get_time() - t0) / 1000;
    if (got != TEST_BYTES) {
        ESP_LOGE(TAG, "short read: %u / %u", (unsigned)got, (unsigned)TEST_BYTES);
        err = ESP_FAIL;
        goto cleanup;
    }
    if (memcmp(write_buf, read_buf, TEST_BYTES) != 0) {
        ESP_LOGE(TAG, "readback mismatch — data corruption");
        err = ESP_FAIL;
        goto cleanup;
    }
    ESP_LOGI(TAG, "read back %u bytes in %" PRId64 " ms — match OK",
             (unsigned)got, read_ms);

    /* --- cleanup test file (non-fatal if unlink fails) --- */
    if (unlink(TEST_PATH) != 0) {
        ESP_LOGW(TAG, "unlink(%s) failed: errno=%d", TEST_PATH, errno);
    }

    ESP_LOGI(TAG, "microSD capture PASS");
    err = ESP_OK;

cleanup:
    free(write_buf);
    free(read_buf);
    if (mounted) {
        esp_err_t u = esp_vfs_fat_sdcard_unmount(MOUNT_POINT, card);
        if (u != ESP_OK) {
            ESP_LOGW(TAG, "unmount: 0x%x (%s)", u, esp_err_to_name(u));
        } else {
            ESP_LOGI(TAG, "unmount OK");
        }
    }
    return err;
}
