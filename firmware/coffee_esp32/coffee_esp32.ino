/*
 * Coffee Bar ESP32 Firmware
 *
 * Required libraries (install via Arduino IDE → Tools → Manage Libraries):
 *   - ArduinoWebsockets by Gil Maimon
 *   - HX711 Arduino Library by Bogdan Necula (search "HX711 by bogde")
 *   - MFRC522 by GithubCommunity
 *   - ArduinoJson by Benoit Blanchon (version 6.x)
 */

#include <WiFi.h>
#include <ArduinoWebsockets.h>
#include <ArduinoJson.h>
#include <SPI.h>
#include <MFRC522.h>
#include <HX711.h>

#include "config.h"

using namespace websockets;

// ---- State machine ----
enum State { CONNECTING_WIFI, CONNECTING_WS, IDLE, AUTHENTICATED, WEIGHING };
State currentState = CONNECTING_WIFI;

// ---- Hardware objects ----
WebsocketsClient ws;
HX711            scale;
MFRC522          rfid(MFRC522_SS, MFRC522_RST);

// ---- Auth ----
String authToken   = "";
String lastRfidUid = "";

// ---- Timers ----
unsigned long lastRfidTime     = 0;
unsigned long lastWeightMs     = 0;
unsigned long lastHeartbeatMs  = 0;
unsigned long lastWsRetryMs    = 0;
unsigned long lastWifiCheckMs  = 0;
unsigned long lastRfidPollMs   = 0;

// ---- Forward declarations ----
void sendEvent(String event, JsonObject extra);
String stateString();

// ---- Helpers ----

String readRfidUid() {
  String uid = "";
  for (byte i = 0; i < rfid.uid.size; i++) {
    if (rfid.uid.uidByte[i] < 0x10) uid += "0";
    uid += String(rfid.uid.uidByte[i], HEX);
  }
  uid.toUpperCase();
  return uid;
}

void sendEvent(String event, JsonObject extra) {
  StaticJsonDocument<256> doc;
  doc["event"] = event;
  for (JsonPair kv : extra) {
    doc[kv.key()] = kv.value();
  }
  String output;
  serializeJson(doc, output);
  ws.send(output);
  Serial.println("[WS] Sent: " + output);
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

  StaticJsonDocument<256> doc;
  if (deserializeJson(doc, msg.data()) != DeserializationError::Ok) return;

  const char* event = doc["event"];
  if (!event) return;

  StaticJsonDocument<64> empty;
  JsonObject noArgs = empty.to<JsonObject>();

  if (strcmp(event, "auth_ok") == 0) {
    authToken    = doc["token"].as<String>();
    currentState = AUTHENTICATED;
    Serial.println("[WS] Authenticated");
  }
  else if (strcmp(event, "auth_fail") == 0) {
    authToken    = "";
    currentState = IDLE;
    Serial.println("[WS] Auth failed");
  }
  else if (strcmp(event, "request_weight") == 0) {
    currentState = WEIGHING;
    Serial.println("[WS] Start weighing");
  }
  else if (strcmp(event, "stop_weight") == 0) {
    currentState = AUTHENTICATED;
    Serial.println("[WS] Stop weighing");
  }
  else if (strcmp(event, "tare_scale") == 0) {
    scale.tare(10);
    sendEvent("tare_done", noArgs);
    Serial.println("[WS] Scale tared");
  }
  else if (strcmp(event, "session_complete") == 0) {
    authToken    = "";
    currentState = IDLE;
    Serial.println("[WS] Session complete — back to IDLE");
  }
  else if (strcmp(event, "session_abandoned") == 0) {
    authToken    = "";
    currentState = IDLE;
    Serial.println("[WS] Session abandoned — back to IDLE");
  }
}

// ---- Setup ----
void setup() {
  Serial.begin(115200);
  delay(200);

  SPI.begin();
  rfid.PCD_Init();
  Serial.println("[RFID] MFRC522 initialized");

  scale.begin(HX711_DOUT, HX711_SCK);
  scale.tare(10);
  scale.set_scale(CALIBRATION_F);
  Serial.println("[Scale] HX711 initialized and tared");

  ws.onMessage(onMessage);
  ws.onEvent([](WebsocketsEvent event, String data) {
    if (event == WebsocketsEvent::ConnectionClosed) {
      Serial.println("[WS] Disconnected");
      currentState = CONNECTING_WS;
    }
  });

  WiFi.begin(WIFI_SSID, WIFI_PASS);
  // state stays CONNECTING_WIFI — non-blocking connect in loop()
}

// ---- Loop ----
void loop() {
  unsigned long now = millis();

  switch (currentState) {

    case CONNECTING_WIFI:
      if (now - lastWifiCheckMs >= 500) {
        lastWifiCheckMs = now;
        if (WiFi.status() == WL_CONNECTED) {
          Serial.println("[WiFi] Connected. IP: " + WiFi.localIP().toString());
          currentState = CONNECTING_WS;
        } else if (WiFi.status() == WL_DISCONNECTED) {
          WiFi.begin(WIFI_SSID, WIFI_PASS);
        }
      }
      break;

    case CONNECTING_WS:
      if (WiFi.status() != WL_CONNECTED) {
        Serial.println("[WiFi] Lost");
        currentState = CONNECTING_WIFI;
        break;
      }
      if (now - lastWsRetryMs >= 5000) {
        lastWsRetryMs = now;
        Serial.println("[WS] Connecting to " + String(SERVER_URL));
        if (ws.connect(SERVER_URL)) {
          Serial.println("[WS] Connected");
          StaticJsonDocument<64> helloDoc;
          JsonObject helloArgs = helloDoc.to<JsonObject>();
          helloArgs["esp_id"] = ESP_ID;
          sendEvent("hello", helloArgs);
          currentState = IDLE;
        } else {
          Serial.println("[WS] Connection failed, retrying in 5s");
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
        currentState = CONNECTING_WIFI;
        break;
      }
      if (!ws.available()) {
        currentState = CONNECTING_WS;
        break;
      }

      // RFID polling (IDLE and AUTHENTICATED only)
      if (currentState != WEIGHING) {
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
            }
            rfid.PICC_HaltA();
            rfid.PCD_StopCrypto1();
          }
        }
      }

      // Weight streaming (WEIGHING only)
      if (currentState == WEIGHING) {
        if (now - lastWeightMs >= 50) {
          lastWeightMs = now;
          float grams = scale.get_units(3);
          Serial.println("[Scale] " + String(grams, 1) + "g");
          StaticJsonDocument<64> wDoc;
          JsonObject wArgs = wDoc.to<JsonObject>();
          wArgs["value"] = round(grams * 10.0f) / 10.0f;
          wArgs["unit"]  = "g";
          sendEvent("weight_reading", wArgs);
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
