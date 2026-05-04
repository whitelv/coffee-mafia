#include <Arduino.h>

/*
 * Coffee Bar ESP32 Firmware
 *
 * Required libraries (install via PlatformIO — see platformio.ini):
 *   - ArduinoWebsockets by Gil Maimon
 *   - HX711 Arduino Library by Bogdan Necula (search "HX711 by bogde")
 *   - MFRC522 by GithubCommunity
 *   - ArduinoJson by Benoit Blanchon (version 6.x)
 */

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <ArduinoWebsockets.h>
#include <ArduinoJson.h>
#include <memory>
#include <SPI.h>
#include <Wire.h>
#include <MFRC522.h>
#include <HX711.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <tiny_websockets/network/generic_esp/generic_esp_clients.hpp>

#include "config.h"

using namespace websockets;

// ---- OLED display ----
constexpr uint8_t OLED_ADDR   = 0x3C;
constexpr int     OLED_WIDTH  = 128;
constexpr int     OLED_HEIGHT = 64;
constexpr uint8_t OLED_SDA    = 21;
constexpr uint8_t OLED_SCL    = 22;
constexpr uint16_t OLED_WEIGHT_REFRESH_MS = 250;
constexpr uint16_t OLED_AUTH_TIMEOUT_MS = 8000;
constexpr uint8_t OLED_CONTRAST = 150;
constexpr uint16_t WEIGHT_READ_INTERVAL_MS = 250;
constexpr uint16_t HX711_READ_TIMEOUT_MS = 120;
constexpr uint16_t HX711_TARE_TIMEOUT_MS = 300;
constexpr uint8_t HX711_TARE_SAMPLES = 10;
constexpr uint16_t I2C_TIMEOUT_MS = 50;

// ---- State machine ----
enum State { CONNECTING_WIFI, CONNECTING_WS, IDLE, AUTHENTICATED, WEIGHING };
State currentState = CONNECTING_WIFI;

// ---- Hardware objects ----
#if WS_USE_SSL
class InsecureEsp32TcpClient : public network::GenericEspTcpClient<WiFiClientSecure> {
public:
  InsecureEsp32TcpClient() {
    client.setInsecure();
  }

  bool connect(const WSString& host, int port) override {
    client.setInsecure();
    return network::GenericEspTcpClient<WiFiClientSecure>::connect(host, port);
  }
};

WebsocketsClient ws(std::make_shared<InsecureEsp32TcpClient>());
#else
WebsocketsClient ws;
#endif
HX711            scale;
MFRC522          rfid(MFRC522_SS, MFRC522_RST);
Adafruit_SSD1306 display(OLED_WIDTH, OLED_HEIGHT, &Wire, -1);

// ---- Auth ----
String authToken   = "";
String lastRfidUid = "";
String currentWeightTarget = "";

// ---- Timers ----
unsigned long lastRfidTime     = 0;
unsigned long lastWeightMs     = 0;
unsigned long lastHeartbeatMs  = 0;
unsigned long lastWsRetryMs    = 0;
unsigned long lastWifiCheckMs  = 0;
unsigned long lastRfidPollMs   = 0;
unsigned long lastOledWeightMs = 0;
unsigned long lastWifiBeginMs  = 0;
unsigned long lastAuthRequestMs = 0;

// ---- OLED state ----
bool oledReady = false;
bool waitingForAuth = false;
bool pendingTare = false;
String oledLine1 = "";
String oledLine2 = "";
String oledLine3 = "";
long scaleOffset = 0;
unsigned long lastScaleNotReadyMs = 0;

// ---- Forward declarations ----
bool sendEvent(String event, JsonObject extra);
String stateString();
void showOLED(String line1, String line2 = "", String line3 = "");
bool tareScale(uint8_t samples = HX711_TARE_SAMPLES);
bool readScaleGrams(float& grams);
void markWsDisconnected(String reason);

// ---- Helpers ----

String wifiStatusString(wl_status_t status) {
  switch (status) {
    case WL_IDLE_STATUS:     return "idle";
    case WL_NO_SSID_AVAIL:   return "no_ssid";
    case WL_SCAN_COMPLETED:  return "scan_done";
    case WL_CONNECTED:       return "connected";
    case WL_CONNECT_FAILED:  return "failed";
    case WL_CONNECTION_LOST: return "lost";
    case WL_DISCONNECTED:    return "disconnected";
    default:                 return "unknown";
  }
}

String formatWeightLine(float grams) {
  return "Now: " + String(grams, 1) + "g";
}

String formatTargetLine(JsonVariant target) {
  if (target.isNull()) return "";
  return "Target: " + String(target.as<float>(), 1) + "g";
}

bool waitForScaleReady(uint16_t timeoutMs) {
  unsigned long started = millis();
  while (millis() - started < timeoutMs) {
    if (scale.is_ready()) return true;
    delay(1);
    yield();
  }
  return false;
}

bool readScaleRaw(long& raw, uint16_t timeoutMs) {
  if (!waitForScaleReady(timeoutMs)) return false;
  raw = scale.read();
  return true;
}

bool tareScale(uint8_t samples) {
  long sum = 0;
  for (uint8_t i = 0; i < samples; i++) {
    long raw = 0;
    if (!readScaleRaw(raw, HX711_TARE_TIMEOUT_MS)) return false;
    sum += raw;
    yield();
  }
  scaleOffset = sum / samples;
  scale.set_offset(scaleOffset);
  return true;
}

bool readScaleGrams(float& grams) {
  long raw = 0;
  if (!readScaleRaw(raw, HX711_READ_TIMEOUT_MS)) return false;
  grams = (raw - scaleOffset) / CALIBRATION_F;
  return true;
}

void showOLED(String line1, String line2, String line3) {
  if (!oledReady) return;
  if (line1 == oledLine1 && line2 == oledLine2 && line3 == oledLine3) return;

  oledLine1 = line1;
  oledLine2 = line2;
  oledLine3 = line3;

  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);

  int count = (line1.length() > 0 ? 1 : 0) +
              (line2.length() > 0 ? 1 : 0) +
              (line3.length() > 0 ? 1 : 0);
  int y = (OLED_HEIGHT - (count * 10)) / 2;

  if (line1.length() > 0) {
    int x = (OLED_WIDTH - ((int)line1.length() * 6)) / 2;
    display.setCursor(x < 0 ? 0 : x, y);
    display.print(line1);
    y += 10;
  }
  if (line2.length() > 0) {
    int x = (OLED_WIDTH - ((int)line2.length() * 6)) / 2;
    display.setCursor(x < 0 ? 0 : x, y);
    display.print(line2);
    y += 10;
  }
  if (line3.length() > 0) {
    int x = (OLED_WIDTH - ((int)line3.length() * 6)) / 2;
    display.setCursor(x < 0 ? 0 : x, y);
    display.print(line3);
  }
  display.display();
}

String readRfidUid() {
  String uid = "";
  for (byte i = 0; i < rfid.uid.size; i++) {
    if (rfid.uid.uidByte[i] < 0x10) uid += "0";
    uid += String(rfid.uid.uidByte[i], HEX);
  }
  uid.toUpperCase();
  return uid;
}

void markWsDisconnected(String reason) {
  Serial.println("[WS] Disconnected: " + reason);
  showOLED("WebSocket", "Disconnected", "");
  currentState = CONNECTING_WS;
}

bool sendEvent(String event, JsonObject extra) {
  StaticJsonDocument<256> doc;
  doc["event"] = event;
  for (JsonPair kv : extra) {
    doc[kv.key()] = kv.value();
  }
  String output;
  serializeJson(doc, output);
  bool sent = ws.send(output);
  if (!sent) {
    Serial.println("[WS] Send failed: " + output);
    markWsDisconnected("send failed");
    return false;
  }
  Serial.println("[WS] Sent: " + output);
  return true;
}

String stateString() {
  switch (currentState) {
    case IDLE:          return "idle";
    case AUTHENTICATED: return "authenticated";
    case WEIGHING:      return "weighing";
    default:            return "connecting";
  }
}

// ---- WebSocket message handler ----
void onMessage(WebsocketsMessage msg) {
  Serial.println("[WS] Recv: " + msg.data());

  StaticJsonDocument<1024> doc;
  DeserializationError err = deserializeJson(doc, msg.data());
  if (err != DeserializationError::Ok) {
    Serial.println("[WS] JSON parse failed: " + String(err.c_str()));
    showOLED("Error", "Bad WS message", "");
    return;
  }

  const char* event = doc["event"];
  if (!event) return;

  StaticJsonDocument<64> empty;
  JsonObject noArgs = empty.to<JsonObject>();

  if (strcmp(event, "auth_ok") == 0) {
    authToken    = doc["token"].as<String>();
    currentState = AUTHENTICATED;
    waitingForAuth = false;
    const char* workerName = doc["user"]["name"] | "";
    showOLED("Worker", "Logged in", String(workerName));
    Serial.println("[WS] Authenticated");
  }
  else if (strcmp(event, "hello_ack") == 0) {
    currentState = IDLE;
    showOLED("WebSocket", "Connected", "Scan RFID");
    Serial.println("[WS] Hello acknowledged");
  }
  else if (strcmp(event, "auth_fail") == 0) {
    authToken    = "";
    currentState = IDLE;
    waitingForAuth = false;
    showOLED("Error", "RFID rejected", "Scan RFID");
    Serial.println("[WS] Auth failed");
  }
  else if (strcmp(event, "request_weight") == 0) {
    currentState = WEIGHING;
    currentWeightTarget = formatTargetLine(doc["target"]);
    lastOledWeightMs = 0;
    showOLED("Brew step", "Weight active", currentWeightTarget);
    Serial.println("[WS] Start weighing");
  }
  else if (strcmp(event, "stop_weight") == 0) {
    currentState = AUTHENTICATED;
    currentWeightTarget = "";
    showOLED("Step completed", "", "");
    Serial.println("[WS] Stop weighing");
  }
  else if (strcmp(event, "tare_scale") == 0) {
    pendingTare = true;
    showOLED("Taring scale", "", "");
    Serial.println("[WS] Tare requested");
  }
  else if (strcmp(event, "session_complete") == 0) {
    authToken    = "";
    currentState = IDLE;
    currentWeightTarget = "";
    showOLED("Session", "Completed", "Scan RFID");
    Serial.println("[WS] Session complete — back to IDLE");
  }
  else if (strcmp(event, "session_abandoned") == 0) {
    authToken    = "";
    currentState = IDLE;
    currentWeightTarget = "";
    showOLED("Session", "Abandoned", "Scan RFID");
    Serial.println("[WS] Session abandoned — back to IDLE");
  }
  else if (strcmp(event, "display_status") == 0) {
    const char* line1 = doc["line1"] | "";
    const char* line2 = doc["line2"] | "";
    const char* line3 = doc["line3"] | "";
    showOLED(String(line1), String(line2), String(line3));
    Serial.println("[OLED] Display status updated");
  }
}

// ---- Setup ----
void setup() {
  Serial.begin(115200);
  delay(200);

  Wire.begin(OLED_SDA, OLED_SCL);
  Wire.setTimeOut(I2C_TIMEOUT_MS);
  if (display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR)) {
    oledReady = true;
    display.clearDisplay();
    display.display();
    display.ssd1306_command(SSD1306_SETCONTRAST);
    display.ssd1306_command(OLED_CONTRAST);
    showOLED("Booting", "", "");
  } else {
    oledReady = false;
    Serial.println("[OLED] SSD1306 init failed; continuing without display");
  }

  SPI.begin();
  rfid.PCD_Init();
  Serial.println("[RFID] MFRC522 initialized");

  scale.begin(HX711_DOUT, HX711_SCK);
  scale.set_scale(CALIBRATION_F);
  if (tareScale()) {
    Serial.println("[Scale] HX711 initialized and tared");
  } else {
    Serial.println("[Scale] HX711 not ready; continuing without tare");
    showOLED("Scale error", "HX711 not ready", "");
  }

  ws.onMessage(onMessage);
  ws.onEvent([](WebsocketsEvent event, String data) {
    if (event == WebsocketsEvent::ConnectionClosed) {
      Serial.println("[WS] Disconnected");
      showOLED("WebSocket", "Disconnected", "");
      currentState = CONNECTING_WS;
    }
  });
  showOLED("Connecting WiFi", "", "");
  Serial.println("[WiFi] Connecting to SSID: " + String(WIFI_SSID));
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  lastWifiBeginMs = millis();
  // state stays CONNECTING_WIFI — non-blocking connect in loop()
}

// ---- Loop ----
void loop() {
  unsigned long now = millis();

  switch (currentState) {

    case CONNECTING_WIFI:
      if (now - lastWifiCheckMs >= 500) {
        lastWifiCheckMs = now;
        wl_status_t wifiStatus = WiFi.status();
        if (wifiStatus == WL_CONNECTED) {
          Serial.println("[WiFi] Connected. IP: " + WiFi.localIP().toString());
          showOLED("Connecting WS", "", "");
          currentState = CONNECTING_WS;
        } else {
          Serial.println("[WiFi] Status: " + wifiStatusString(wifiStatus));
          showOLED("Connecting WiFi", "", "");
        }

        if (wifiStatus != WL_CONNECTED && now - lastWifiBeginMs >= 5000) {
          lastWifiBeginMs = now;
          Serial.println("[WiFi] Retrying connection");
          WiFi.disconnect();
          WiFi.begin(WIFI_SSID, WIFI_PASS);
        }
      }
      break;

    case CONNECTING_WS:
      if (WiFi.status() != WL_CONNECTED) {
        Serial.println("[WiFi] Lost");
        showOLED("Connecting WiFi", "", "");
        currentState = CONNECTING_WIFI;
        break;
      }
      if (now - lastWsRetryMs >= 5000) {
        lastWsRetryMs = now;
        Serial.println("[WS] Connecting to " + String(SERVER_URL));
#if WS_USE_SSL
        if (ws.connect(WS_HOST, WS_PORT, WS_PATH)) {
#else
        if (ws.connect(SERVER_URL)) {
#endif
          Serial.println("[WS] Connected");
          StaticJsonDocument<64> helloDoc;
          JsonObject helloArgs = helloDoc.to<JsonObject>();
          helloArgs["esp_id"] = ESP_ID;
          if (sendEvent("hello", helloArgs)) {
            currentState = IDLE;
            showOLED("WebSocket", "Waiting server", "");
          }
        } else {
          Serial.println("[WS] Connection failed, retrying in 5s");
          showOLED("WebSocket", "Disconnected", "");
        }
      }
      break;

    case IDLE:
    case AUTHENTICATED:
    case WEIGHING:
      ws.poll();

      // Drop back if connectivity lost
      if (WiFi.status() != WL_CONNECTED) {
        Serial.println("[WiFi] Lost");
        showOLED("Connecting WiFi", "", "");
        currentState = CONNECTING_WIFI;
        break;
      }
      if (!ws.available()) {
        markWsDisconnected("socket unavailable");
        break;
      }

      if (pendingTare) {
        pendingTare = false;
        StaticJsonDocument<64> empty;
        JsonObject noArgs = empty.to<JsonObject>();
        if (tareScale()) {
          sendEvent("tare_done", noArgs);
          showOLED("Tare done", "", "");
          Serial.println("[WS] Scale tared");
        } else {
          showOLED("Scale error", "HX711 not ready", "");
          Serial.println("[Scale] Tare failed: HX711 not ready");
        }
      }

      // RFID polling (IDLE and AUTHENTICATED only)
      if (currentState != WEIGHING) {
        if (waitingForAuth && now - lastAuthRequestMs >= OLED_AUTH_TIMEOUT_MS) {
          waitingForAuth = false;
          showOLED("Auth timeout", "Scan RFID", "");
          Serial.println("[RFID] Auth timeout waiting for backend response");
        }
        if (now - lastRfidPollMs >= 200) {
          lastRfidPollMs = now;
          if (rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) {
            String uid = readRfidUid();
            bool debounced = (uid == lastRfidUid) && (now - lastRfidTime < 3000);
            if (!debounced) {
              Serial.println("[RFID] UID: " + uid);
              StaticJsonDocument<64> rfidDoc;
              JsonObject rfidArgs = rfidDoc.to<JsonObject>();
              rfidArgs["uid"] = uid;
              sendEvent("rfid_scan", rfidArgs);
              lastRfidUid  = uid;
              lastRfidTime = now;
              lastAuthRequestMs = now;
              waitingForAuth = true;
              showOLED("RFID scanned", "Waiting auth", "");
            }
            rfid.PICC_HaltA();
            rfid.PCD_StopCrypto1();
          }
        }
      }

      // Weight streaming (WEIGHING only)
      if (currentState == WEIGHING) {
        if (now - lastWeightMs >= WEIGHT_READ_INTERVAL_MS) {
          lastWeightMs = now;
          float grams = 0.0f;
          if (!readScaleGrams(grams)) {
            if (now - lastScaleNotReadyMs >= 1000) {
              lastScaleNotReadyMs = now;
              Serial.println("[Scale] HX711 not ready");
              showOLED("Scale error", "HX711 not ready", "");
            }
            break;
          }
          Serial.println("[Scale] " + String(grams, 1) + "g");
          StaticJsonDocument<64> wDoc;
          JsonObject wArgs = wDoc.to<JsonObject>();
          wArgs["value"] = round(grams * 10.0f) / 10.0f;
          wArgs["unit"]  = "g";
          sendEvent("weight_reading", wArgs);
          if (now - lastOledWeightMs >= OLED_WEIGHT_REFRESH_MS) {
            lastOledWeightMs = now;
            showOLED("Weight active", formatWeightLine(grams), currentWeightTarget);
          }
        }
      }

      // Heartbeat (all active states)
      if (now - lastHeartbeatMs >= 10000) {
        lastHeartbeatMs = now;
        StaticJsonDocument<64> hbDoc;
        JsonObject hbArgs = hbDoc.to<JsonObject>();
        hbArgs["state"] = stateString();
        sendEvent("heartbeat", hbArgs);
      }

      break;
  }
}
