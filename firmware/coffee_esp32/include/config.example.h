#pragma once

// WiFi
#define WIFI_SSID     "YOUR_WIFI_SSID"
#define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"

// WebSocket - switch between dev and production
// Development:
// #define WS_HOST "192.168.1.100"
// #define WS_PORT 8000
// #define WS_PATH "/ws/esp/ESP32_BAR_01"

// Production (Render):
#define WS_HOST "coffee-bar-backend.onrender.com"
#define WS_PORT 443
#define WS_PATH "/ws/esp/ESP32_BAR_01"
#define WS_USE_SSL true

// Hardware pins
#define HX711_DOUT 4
#define HX711_SCK  2
#define RFID_SS    5
#define RFID_RST   16

// Calibration
#define CALIBRATION_F 2280.0f
#define ESP_ID "ESP32_BAR_01"
