idf_component_register(
    SRCS         "main.c" "phase2_camera.c" "phase3_mic.c" "phase4_sd.c"
                 "phase5_net.c" "phase5_cam_pump.c" "phase5_http.c"
                 "phase5_motion.c" "phase5_led.c"
                 "phase6_settings.c" "phase6_mqtt.c"
    INCLUDE_DIRS "."
    REQUIRES     esp_driver_gpio esp_driver_i2s esp_driver_sdmmc sdmmc fatfs vfs
                 esp_psram spi_flash esp_system esp_hw_support esp_timer
                 esp_wifi esp_netif esp_event nvs_flash esp_http_server
                 esp_app_format espressif__mqtt
                 log freertos
                 espressif__esp32-camera
)
