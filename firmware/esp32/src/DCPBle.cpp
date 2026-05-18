// DCP over BLE GATT — ESP32 peripheral.

#include "DCPBle.h"

#ifdef ARDUINO

#include "DCPCrypto.h"

#if __has_include(<NimBLEDevice.h>)
#include <NimBLEDevice.h>
#include <string.h>

namespace dcp {

namespace {

// Tiny helper: copy a 36-char canonical UUID, replacing the last two hex
// digits. Input must be exactly 36 chars (8-4-4-4-12), case preserved.
void derived_uuid(const char* base, uint8_t last_byte, char out[37]) {
    memcpy(out, base, 36);
    static const char hex[] = "0123456789abcdef";
    out[34] = hex[(last_byte >> 4) & 0xF];
    out[35] = hex[last_byte & 0xF];
    out[36] = 0;
}

class WriteCb : public NimBLECharacteristicCallbacks {
public:
    explicit WriteCb(DCPBle* owner) : _owner(owner) {}
    void onWrite(NimBLECharacteristic* c) override {
        std::string v = c->getValue();
        _owner->on_write(reinterpret_cast<const uint8_t*>(v.data()), v.size());
    }
private:
    DCPBle* _owner;
};

} // anonymous namespace

DCPBle::DCPBle(const char* service_uuid,
               IntentBinding* bindings,
               size_t binding_count)
    : _service_uuid(service_uuid),
      _bindings(bindings),
      _binding_count(binding_count) {
    derived_uuid(service_uuid, 0xc1, _c2d_uuid);
    derived_uuid(service_uuid, 0xd1, _d2c_uuid);
}

void DCPBle::set_wire_secret(const uint8_t* secret, size_t len) {
    if (len > sizeof(_wire_secret)) len = sizeof(_wire_secret);
    memcpy(_wire_secret, secret, len);
    _secret_len = len;
}

void DCPBle::begin() {
    NimBLEServer* server = NimBLEDevice::createServer();
    NimBLEService* svc = server->createService(_service_uuid);

    NimBLECharacteristic* c2d = svc->createCharacteristic(
        _c2d_uuid, NIMBLE_PROPERTY::WRITE);
    static WriteCb cb(this);
    c2d->setCallbacks(&cb);

    NimBLECharacteristic* d2c = svc->createCharacteristic(
        _d2c_uuid, NIMBLE_PROPERTY::NOTIFY);
    _notify_char = d2c;

    svc->start();

    NimBLEAdvertising* adv = NimBLEDevice::getAdvertising();
    adv->addServiceUUID(_service_uuid);
    adv->start();
}

void DCPBle::on_write(const uint8_t* data, size_t len) {
    if (_secret_len > 0) {
        if (len < HMAC_BYTES) return;
        size_t signed_len = len - HMAC_BYTES;
        uint8_t expected[HMAC_BYTES];
        hmac_sha256_truncated(_wire_secret, _secret_len, data, signed_len,
                              expected, HMAC_BYTES);
        if (!ct_equal(expected, data + signed_len, HMAC_BYTES)) return;
        handle_frame(data, signed_len);
    } else {
        handle_frame(data, len);
    }
}

bool DCPBle::handle_frame(const uint8_t* frame, size_t len) {
    if (len < HEADER_SIZE) return false;
    uint8_t  ver  = frame[0];
    uint8_t  kind = frame[1];
    uint16_t seq  = ((uint16_t)frame[2] << 8) | frame[3];
    uint16_t iid  = ((uint16_t)frame[4] << 8) | frame[5];
    if (ver != WIRE_VERSION) return false;

    IntentHandler handler = nullptr;
    void* user = nullptr;
    for (size_t i = 0; i < _binding_count; ++i) {
        if (_bindings[i].id == iid) {
            handler = _bindings[i].handler;
            user = _bindings[i].user;
            break;
        }
    }
    if (handler == nullptr) {
        send_error(seq, iid, STATUS_UNKNOWN_INTENT);
        return false;
    }

    CborReader params(frame + HEADER_SIZE, len - HEADER_SIZE);
    if (!params.begin()) {
        send_error(seq, iid, STATUS_DENIED);
        return false;
    }

    uint8_t reply_buf[MAX_FRAME_BYTES];
    CborMap reply(reply_buf, sizeof(reply_buf));
    reply.begin();
    Status status = handler(kind, params, reply, user);
    reply.finish();

    if (status == STATUS_OK) {
        send_frame(KIND_REPLY, seq, iid, reply_buf, reply.size());
    } else {
        send_error(seq, iid, status);
    }
    return true;
}

bool DCPBle::send_frame(uint8_t kind, uint16_t seq, uint16_t iid,
                        const uint8_t* payload, size_t payload_len) {
    if (_notify_char == nullptr) return false;
    uint8_t out[MAX_FRAME_BYTES];
    size_t need = HEADER_SIZE + payload_len + (_secret_len > 0 ? HMAC_BYTES : 0);
    if (need > sizeof(out)) return false;
    out[0] = WIRE_VERSION;
    out[1] = kind;
    out[2] = (uint8_t)(seq >> 8); out[3] = (uint8_t)seq;
    out[4] = (uint8_t)(iid >> 8); out[5] = (uint8_t)iid;
    memcpy(out + HEADER_SIZE, payload, payload_len);
    size_t total = HEADER_SIZE + payload_len;
    if (_secret_len > 0) {
        hmac_sha256_truncated(_wire_secret, _secret_len, out, total,
                              out + total, HMAC_BYTES);
        total += HMAC_BYTES;
    }
    auto* ch = static_cast<NimBLECharacteristic*>(_notify_char);
    ch->setValue(out, total);
    ch->notify();
    return true;
}

void DCPBle::send_error(uint16_t seq, uint16_t iid, Status status) {
    uint8_t buf[8];
    CborMap m(buf, sizeof(buf));
    m.begin();
    m.add_int("status", (int64_t)status);
    m.finish();
    send_frame(KIND_ERROR, seq, iid, buf, m.size());
}

bool DCPBle::send_event(const char* event_name, CborMap& payload) {
    payload.finish();
    return send_frame(KIND_EVENT, 0, intent_id(event_name),
                      payload.data(), payload.size());
}

} // namespace dcp

#else
#warning "DCPBle requires NimBLE-Arduino — install from Library Manager."
#endif // __has_include(<NimBLEDevice.h>)

#endif // ARDUINO
