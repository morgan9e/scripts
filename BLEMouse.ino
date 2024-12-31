#include "BLEDevice.h"
#include "BLEHIDDevice.h"
#include "HIDTypes.h"

#define DEVICE_NAME "ESP32 Mouse"
#define BLE_MANUFACTURER "TinyUSB"

BLEHIDDevice* hid;
BLECharacteristic* input;
BLECharacteristic* output;
bool isBleConnected = false;

#define MOUSE_LEFT 1
#define MOUSE_RIGHT 2
#define MOUSE_MIDDLE 4

struct InputReport {
    uint8_t buttons;
    int8_t x;
    int8_t y;
    int8_t w;
    int8_t hw;
};


void setup() {
  Serial.begin(115200);
  Serial2.begin(115200, SERIAL_8N1, 22, 23);
  xTaskCreate(bluetoothTask, "bluetooth", 20000, NULL, 5, NULL);
}

void loop() {
  while (Serial2.available()) {
    String uartData = Serial2.readStringUntil('\n');
    if (uartData.startsWith("REPORT: ")) {
      int r, m, l, w, x, y;
      sscanf(uartData.c_str(), "REPORT: BTN %d %d %d WHEEL %d X %d Y %d", &l, &m, &r, &w, &x, &y);

      uint8_t button = 0;
      
      if (r) button |= MOUSE_RIGHT;
      else button &= ~MOUSE_RIGHT;

      if (m) button |= MOUSE_MIDDLE;
      else button &= ~MOUSE_MIDDLE;

      if (l) button |= MOUSE_LEFT;
      else button &= ~MOUSE_LEFT;

      InputReport report = {
        .buttons = button,
        .x = x,
        .y = y,
        .w = w,
        .hw = 0
      };
      
      if (isBleConnected) {
        input->setValue((uint8_t*)&report, sizeof(report));
        input->notify();
      }
    }
    // Serial.println(uartData);
  }
}

static const uint8_t _hidReportDescriptor[] = {
  USAGE_PAGE(1),       0x01, // USAGE_PAGE (Generic Desktop)
  USAGE(1),            0x02, // USAGE (Mouse)
  COLLECTION(1),       0x01, // COLLECTION (Application)
  USAGE(1),            0x01, //   USAGE (Pointer)
  COLLECTION(1),       0x00, //   COLLECTION (Physical)
  // ------------------------------------------------- Buttons (Left, Right, Middle, Back, Forward)
  USAGE_PAGE(1),       0x09, //     USAGE_PAGE (Button)
  USAGE_MINIMUM(1),    0x01, //     USAGE_MINIMUM (Button 1)
  USAGE_MAXIMUM(1),    0x05, //     USAGE_MAXIMUM (Button 5)
  LOGICAL_MINIMUM(1),  0x00, //     LOGICAL_MINIMUM (0)
  LOGICAL_MAXIMUM(1),  0x01, //     LOGICAL_MAXIMUM (1)
  REPORT_SIZE(1),      0x01, //     REPORT_SIZE (1)
  REPORT_COUNT(1),     0x05, //     REPORT_COUNT (5)
  HIDINPUT(1),         0x02, //     INPUT (Data, Variable, Absolute) ;5 button bits
  // ------------------------------------------------- Padding
  REPORT_SIZE(1),      0x03, //     REPORT_SIZE (3)
  REPORT_COUNT(1),     0x01, //     REPORT_COUNT (1)
  HIDINPUT(1),         0x03, //     INPUT (Constant, Variable, Absolute) ;3 bit padding
  // ------------------------------------------------- X/Y position, Wheel
  USAGE_PAGE(1),       0x01, //     USAGE_PAGE (Generic Desktop)
  USAGE(1),            0x30, //     USAGE (X)
  USAGE(1),            0x31, //     USAGE (Y)
  USAGE(1),            0x38, //     USAGE (Wheel)
  LOGICAL_MINIMUM(1),  0x81, //     LOGICAL_MINIMUM (-127)
  LOGICAL_MAXIMUM(1),  0x7f, //     LOGICAL_MAXIMUM (127)
  REPORT_SIZE(1),      0x08, //     REPORT_SIZE (8)
  REPORT_COUNT(1),     0x03, //     REPORT_COUNT (3)
  HIDINPUT(1),         0x06, //     INPUT (Data, Variable, Relative) ;3 bytes (X,Y,Wheel)
  // ------------------------------------------------- Horizontal wheel
  USAGE_PAGE(1),       0x0c, //     USAGE PAGE (Consumer Devices)
  USAGE(2),      0x38, 0x02, //     USAGE (AC Pan)
  LOGICAL_MINIMUM(1),  0x81, //     LOGICAL_MINIMUM (-127)
  LOGICAL_MAXIMUM(1),  0x7f, //     LOGICAL_MAXIMUM (127)
  REPORT_SIZE(1),      0x08, //     REPORT_SIZE (8)
  REPORT_COUNT(1),     0x01, //     REPORT_COUNT (1)
  HIDINPUT(1),         0x06, //     INPUT (Data, Var, Rel)
  END_COLLECTION(0),         //   END_COLLECTION
  END_COLLECTION(0)          // END_COLLECTION
};

class BleHIDCallbacks : public BLEServerCallbacks {
    void onConnect(BLEServer* server) {
        isBleConnected = true;
        BLE2902* cccDesc = (BLE2902*)input->getDescriptorByUUID(BLEUUID((uint16_t)0x2902));
        cccDesc->setNotifications(true);
        Serial.println("CONNECTED");
    }

    void onDisconnect(BLEServer* server) {
        isBleConnected = false;
        BLE2902* cccDesc = (BLE2902*)input->getDescriptorByUUID(BLEUUID((uint16_t)0x2902));
        cccDesc->setNotifications(false);
        Serial.println("DISCONNECTED");
    }
};

void bluetoothTask(void*) {
    BLEDevice::init(DEVICE_NAME);
    BLEServer* server = BLEDevice::createServer();
    server->setCallbacks(new BleHIDCallbacks());

    hid = new BLEHIDDevice(server);
    input = hid->inputReport(0);

    hid->manufacturer()->setValue(BLE_MANUFACTURER);
    hid->pnp(0x02, 0xe502, 0xa111, 0x0210);
    hid->hidInfo(0x00, 0x02);

    BLESecurity* security = new BLESecurity();
    security->setAuthenticationMode(ESP_LE_AUTH_BOND);

    hid->reportMap((uint8_t*)_hidReportDescriptor, sizeof(_hidReportDescriptor));
    hid->startServices();
    hid->setBatteryLevel(100);

    BLEAdvertising* advertising = server->getAdvertising();
    advertising->setAppearance(HID_MOUSE);
    advertising->addServiceUUID(hid->hidService()->getUUID());
    advertising->addServiceUUID(hid->deviceInfo()->getUUID());
    advertising->addServiceUUID(hid->batteryService()->getUUID());
    advertising->start();

    Serial.println("BLE READY");
    delay(portMAX_DELAY);
};
