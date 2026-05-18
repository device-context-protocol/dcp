// DCP over BLE GATT — ESP32 peripheral side.
//
// Layout matches the Python BleTransport convention:
//
//   service UUID:     user-supplied per device
//   c2d (host→dev):   service UUID with last byte replaced by 0xc1   (WRITE)
//   d2c (dev→host):   service UUID with last byte replaced by 0xd1   (NOTIFY)
//
// BLE already handles MTU/framing, so we do NOT COBS-encode or append CRC
// here — those exist only to recover frame boundaries on raw byte streams
// like UART. The HMAC tail (optional) is still appended when wire signing
// is enabled.
//
// Requires NimBLE-Arduino (https://github.com/h2zero/NimBLE-Arduino) — install
// from the Arduino Library Manager. Compatible API up to NimBLE-Arduino 1.x;
// 2.x uses slightly different class names (NimBLECharacteristicCallbacks
// signatures shift).

#ifndef DCP_BLE_H
#define DCP_BLE_H

#include "DCP.h"

#ifdef ARDUINO

namespace dcp {

class DCPBle {
public:
    DCPBle(const char* service_uuid,
           IntentBinding* bindings,
           size_t binding_count);

    // Call once in setup() after NimBLEDevice::init().
    void begin();

    // Optional wire-level HMAC (matches Python Bridge wire_secret).
    void set_wire_secret(const uint8_t* secret, size_t len);

    // Called by the NimBLE write callback (wired up internally).
    void on_write(const uint8_t* data, size_t len);

    // Emit an unsolicited event notification.
    bool send_event(const char* event_name, CborMap& payload);

private:
    bool handle_frame(const uint8_t* frame, size_t len);
    bool send_frame(uint8_t kind, uint16_t seq, uint16_t iid,
                    const uint8_t* payload, size_t payload_len);
    void send_error(uint16_t seq, uint16_t iid, Status status);

    const char*    _service_uuid;
    char           _c2d_uuid[37];   // canonical UUID string + NUL
    char           _d2c_uuid[37];
    IntentBinding* _bindings;
    size_t         _binding_count;
    uint8_t        _wire_secret[64];
    size_t         _secret_len = 0;
    void*          _notify_char = nullptr;   // NimBLECharacteristic*, opaque here
};

} // namespace dcp

#endif // ARDUINO
#endif // DCP_BLE_H
