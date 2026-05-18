// DCP — Device Context Protocol, reference firmware for Arduino-compatible MCUs.
//
//   Wire frame:
//     [ COBS( header(6B) || cbor_map || crc16_be ) ] 0x00
//
//   Header (big-endian):
//     u8  ver        = 1
//     u8  kind       = 0x01 call · 0x02 reply · 0x03 event · 0x04 error · 0x81 dry-run
//     u16 seq
//     u16 intent_id  = CRC-16/CCITT of intent name
//
// This file is intentionally small. It does not pull in Arduino-only types
// beyond Stream, so it builds against ESP-IDF or any other framework that
// provides Stream-compatible I/O.

#ifndef DCP_H
#define DCP_H

#include <stdint.h>
#include <stddef.h>
#include <Stream.h>

namespace dcp {

constexpr uint8_t  WIRE_VERSION    = 1;
constexpr size_t   HEADER_SIZE     = 6;
constexpr size_t   MAX_FRAME_BYTES = 256;   // adjust if your device needs larger payloads
constexpr size_t   HMAC_BYTES      = 16;    // truncated HMAC-SHA256, when wire signing is on

enum Kind : uint8_t {
    KIND_CALL    = 0x01,
    KIND_REPLY   = 0x02,
    KIND_EVENT   = 0x03,
    KIND_ERROR   = 0x04,
    KIND_DRY_RUN = 0x81,
};

enum Status : uint8_t {
    STATUS_OK,
    STATUS_DENIED,
    STATUS_RANGE,
    STATUS_BUSY,
    STATUS_UNKNOWN_INTENT,
    STATUS_CAPABILITY_REQUIRED,
};

uint16_t crc16_ccitt(const uint8_t* data, size_t len);
uint16_t intent_id(const char* name);

// Compile-time CRC-16/CCITT. Use as ``DCP_ID("set_brightness")`` to get an
// intent_id at compile time. Requires C++14 or newer.
namespace detail {
constexpr uint16_t crc16_step(uint16_t crc, int n) {
    return n == 0 ? crc
                  : crc16_step((crc & 0x8000) ? (uint16_t)((crc << 1) ^ 0x1021) : (uint16_t)(crc << 1),
                               n - 1);
}
constexpr uint16_t crc16_ce(const char* s, uint16_t crc = 0xFFFF, int i = 0) {
    return s[i] == 0
        ? crc
        : crc16_ce(s, crc16_step((uint16_t)(crc ^ ((uint16_t)(uint8_t)s[i] << 8)), 8), i + 1);
}
} // namespace detail
} // namespace dcp

#define DCP_ID(name) (::dcp::detail::crc16_ce(name))

namespace dcp {

// Tiny CBOR helpers, restricted to the subset DCP uses (map with string keys
// → number / bool / short string). Return ``false`` on overflow or malformed input.
class CborMap {
public:
    CborMap(uint8_t* buf, size_t cap) : _buf(buf), _cap(cap), _len(0), _count(0) {}

    void  begin();                                           // write the map header placeholder
    bool  add_float(const char* key, double value);
    bool  add_int(const char* key, int64_t value);
    bool  add_bool(const char* key, bool value);
    bool  add_string(const char* key, const char* value);
    void  finish();                                          // patch the map header with the actual count

    const uint8_t* data() const { return _buf; }
    size_t         size() const { return _len; }
private:
    bool   put_key(const char* key);
    uint8_t* _buf;
    size_t   _cap;
    size_t   _len;
    size_t   _count;
};

class CborReader {
public:
    CborReader(const uint8_t* buf, size_t len) : _buf(buf), _len(len), _pos(0), _items(0) {}

    bool  begin();                                           // read the map header
    bool  next_key(const char** key, size_t* key_len);
    bool  read_float(double* out);
    bool  read_int(int64_t* out);
    bool  read_bool(bool* out);
    bool  read_string(const char** out, size_t* out_len);
    bool  skip();                                            // skip a value of any supported type

    size_t remaining() const { return _items; }
private:
    const uint8_t* _buf;
    size_t         _len;
    size_t         _pos;
    size_t         _items;
};

// Handler signature. The handler reads parameters from ``params`` (a CBOR map)
// and writes a reply into ``reply`` (a CBOR map you build with ``CborMap``).
// Return one of the ``STATUS_*`` codes; ``STATUS_OK`` produces a REPLY frame,
// anything else produces an ERROR frame with that status.
typedef Status (*IntentHandler)(uint8_t kind, CborReader& params, CborMap& reply, void* user);

struct IntentBinding {
    uint16_t       id;
    IntentHandler  handler;
    void*          user;
};

class DCP {
public:
    DCP(Stream& stream, IntentBinding* bindings, size_t binding_count)
        : _stream(stream), _bindings(bindings), _binding_count(binding_count),
          _secret_len(0) {}

    // Process any bytes that have arrived. Call from loop().
    void poll();

    // Emit an unsolicited event frame.
    bool send_event(const char* event_name, CborMap& payload);

    // Enable per-frame wire-level HMAC. Must match the Bridge's wire_secret.
    // If never called, wire signing is off (compatible with v0.2 bridges).
    void set_wire_secret(const uint8_t* secret, size_t len);

private:
    bool   handle_frame(const uint8_t* frame, size_t len);
    bool   send_frame(uint8_t kind, uint16_t seq, uint16_t iid,
                      const uint8_t* payload, size_t payload_len);
    void   send_error(uint16_t seq, uint16_t iid, Status status);

    Stream&         _stream;
    IntentBinding*  _bindings;
    size_t          _binding_count;
    uint8_t         _rx[MAX_FRAME_BYTES];
    size_t          _rx_len = 0;
    uint8_t         _wire_secret[64];
    size_t          _secret_len;
};

} // namespace dcp

#endif // DCP_H
