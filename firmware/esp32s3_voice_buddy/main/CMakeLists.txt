idf_component_register(
    SRCS
        "app_main.c"
        "link.c"
        "audio.c"
        "face.c"
        "sr.c"
    INCLUDE_DIRS "."
    REQUIRES
        driver            # UART + I2S (i2s_std) + SPI + LEDC + GPIO umbrella
        esp_lcd           # ST7789 panel
        esp_timer
        json              # cJSON for control-message parsing
        esp-sr            # AFE + WakeNet + MultiNet (prebuilt libs + esp32s3 headers)
        freertos
)
