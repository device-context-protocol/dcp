// DCP firmware reference implementation. See DCP.h for the wire format.
//
// Code size target: <16 KB on Cortex-M0 / ESP32-class MCUs. RAM use is
// dominated by MAX_FRAME_BYTES (see DCP.h).

#include "DCP.h"
#include "DCPCrypto.h"
#include <string.h>

namespace dcp {

// ---------------------------------------------------------------------------
// CRC-16/CCITT (poly 0x1021, init 0xFFFF).

uint16_t crc16_ccitt(const uint8_t* data, size_t len) {
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < len; ++i) {
        crc ^= (uint16_t)data[i] << 8;
        for (int b = 0; b < 8; ++b) {
            crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : (crc << 1);
        }
    }
    return crc;
}

uint16_t intent_id(const char* name) {
    return crc16_ccitt((const uint8_t*)name, strlen(name));
}

// ---------------------------------------------------------------------------
// COBS.

static size_t cobs_encode(const uint8_t* in, size_t in_len, uint8_t* out) {
    size_t code_idx = 0;
    uint8_t code = 1;
    size_t out_idx = 1;
    out[0] = 0;
    for (size_t i = 0; i < in_len; ++i) {
        if (in[i] == 0) {
            out[code_idx] = code;
            code_idx = out_idx++;
            out[code_idx] = 0;
            code = 1;
        } else {
            out[out_idx++] = in[i];
            if (++code == 0xFF) {
                out[code_idx] = code;
                code_idx = out_idx++;
                out[code_idx] = 0;
                code = 1;
            }
        }
    }
    out[code_idx] = code;
    return out_idx;
}

static bool cobs_decode(const uint8_t* in, size_t in_len, uint8_t* out, size_t* out_len) {
    size_t i = 0, o = 0;
    while (i < in_len) {
        uint8_t code = in[i];
        if (code == 0 || i + code > in_len) return false;
        for (size_t j = 1; j < code; ++j) out[o++] = in[i + j];
        i += code;
        if (i < in_len && code != 0xFF) out[o++] = 0;
    }
    *out_len = o;
    return true;
}

// ---------------------------------------------------------------------------
// CBOR — tiny subset.
//
// Encoded by us: maps up to 23 entries; keys are short ASCII strings (<24
// bytes); values are uint/sint up to 8 bytes, IEEE-754 double, bool, or short
// text strings.
//
// Decoded by us: same shapes plus the half-precision floats GCC sometimes emits
// (rare; we just refuse them).

static const uint8_t MT_UINT   = 0;
static const uint8_t MT_SINT   = 1;
static const uint8_t MT_STR    = 3;
static const uint8_t MT_MAP    = 5;
static const uint8_t MT_SIMPLE = 7;

static size_t write_head(uint8_t* buf, uint8_t mt, uint64_t value) {
    if (value < 24) {
        buf[0] = (mt << 5) | (uint8_t)value;
        return 1;
    }
    if (value < 0x100) {
        buf[0] = (mt << 5) | 24;
        buf[1] = (uint8_t)value;
        return 2;
    }
    if (value < 0x10000) {
        buf[0] = (mt << 5) | 25;
        buf[1] = (uint8_t)(value >> 8);
        buf[2] = (uint8_t)value;
        return 3;
    }
    buf[0] = (mt << 5) | 26;
    for (int i = 0; i < 4; ++i) buf[1 + i] = (uint8_t)(value >> (24 - i * 8));
    return 5;
}

void CborMap::begin() {
    // reserve 1 byte; we'll patch it in finish(). max 23 entries supported here.
    _len = 1;
    _count = 0;
}

bool CborMap::put_key(const char* key) {
    size_t klen = strlen(key);
    if (klen >= 24) return false;
    if (_len + 1 + klen > _cap) return false;
    _buf[_len++] = (MT_STR << 5) | (uint8_t)klen;
    memcpy(_buf + _len, key, klen);
    _len += klen;
    return true;
}

bool CborMap::add_int(const char* key, int64_t value) {
    if (!put_key(key)) return false;
    uint8_t mt;
    uint64_t v;
    if (value >= 0) { mt = MT_UINT; v = (uint64_t)value; }
    else            { mt = MT_SINT; v = (uint64_t)(-1 - value); }
    if (_len + 9 > _cap) return false;
    _len += write_head(_buf + _len, mt, v);
    ++_count;
    return true;
}

bool CborMap::add_float(const char* key, double value) {
    if (!put_key(key)) return false;
    if (_len + 9 > _cap) return false;
    _buf[_len++] = (MT_SIMPLE << 5) | 27;  // double-precision float
    uint64_t bits;
    memcpy(&bits, &value, 8);
    for (int i = 0; i < 8; ++i) _buf[_len + i] = (uint8_t)(bits >> (56 - i * 8));
    _len += 8;
    ++_count;
    return true;
}

bool CborMap::add_bool(const char* key, bool value) {
    if (!put_key(key)) return false;
    if (_len + 1 > _cap) return false;
    _buf[_len++] = (MT_SIMPLE << 5) | (value ? 21 : 20);
    ++_count;
    return true;
}

bool CborMap::add_string(const char* key, const char* value) {
    if (!put_key(key)) return false;
    size_t vlen = strlen(value);
    if (vlen >= 24) return false;
    if (_len + 1 + vlen > _cap) return false;
    _buf[_len++] = (MT_STR << 5) | (uint8_t)vlen;
    memcpy(_buf + _len, value, vlen);
    _len += vlen;
    ++_count;
    return true;
}

void CborMap::finish() {
    _buf[0] = (MT_MAP << 5) | (uint8_t)_count;
}

// --- CborReader ------------------------------------------------------------

bool CborReader::begin() {
    // Missing/empty body is equivalent to an empty CBOR map (per wire spec).
    if (_len == 0) {
        _items = 0;
        return true;
    }
    uint8_t head = _buf[_pos];
    if ((head >> 5) != MT_MAP) return false;
    uint8_t info = head & 0x1F;
    if (info >= 24) return false;  // we only emit small maps
    _items = info;
    _pos = 1;
    return true;
}

bool CborReader::next_key(const char** key, size_t* key_len) {
    if (_pos >= _len) return false;
    uint8_t head = _buf[_pos++];
    if ((head >> 5) != MT_STR) return false;
    uint8_t info = head & 0x1F;
    if (info >= 24) return false;
    if (_pos + info > _len) return false;
    *key = (const char*)(_buf + _pos);
    *key_len = info;
    _pos += info;
    return true;
}

bool CborReader::read_float(double* out) {
    if (_pos >= _len) return false;
    uint8_t head = _buf[_pos++];
    uint8_t mt = head >> 5;
    uint8_t info = head & 0x1F;
    if (mt == MT_SIMPLE && info == 27) {
        if (_pos + 8 > _len) return false;
        uint64_t bits = 0;
        for (int i = 0; i < 8; ++i) bits = (bits << 8) | _buf[_pos + i];
        memcpy(out, &bits, 8);
        _pos += 8;
        if (_items) --_items;
        return true;
    }
    if (mt == MT_UINT || mt == MT_SINT) {
        // promote integer to double
        _pos--;
        int64_t i;
        if (!read_int(&i)) return false;
        *out = (double)i;
        return true;
    }
    return false;
}

bool CborReader::read_int(int64_t* out) {
    if (_pos >= _len) return false;
    uint8_t head = _buf[_pos++];
    uint8_t mt = head >> 5;
    uint8_t info = head & 0x1F;
    if (mt != MT_UINT && mt != MT_SINT) return false;
    uint64_t v = 0;
    if (info < 24) {
        v = info;
    } else if (info == 24) {
        if (_pos + 1 > _len) return false; v = _buf[_pos]; _pos += 1;
    } else if (info == 25) {
        if (_pos + 2 > _len) return false; v = (uint64_t)_buf[_pos] << 8 | _buf[_pos+1]; _pos += 2;
    } else if (info == 26) {
        if (_pos + 4 > _len) return false;
        v = (uint64_t)_buf[_pos]<<24 | (uint64_t)_buf[_pos+1]<<16 | (uint64_t)_buf[_pos+2]<<8 | _buf[_pos+3];
        _pos += 4;
    } else {
        return false;
    }
    *out = (mt == MT_UINT) ? (int64_t)v : -1 - (int64_t)v;
    if (_items) --_items;
    return true;
}

bool CborReader::read_bool(bool* out) {
    if (_pos >= _len) return false;
    uint8_t head = _buf[_pos++];
    if ((head >> 5) != MT_SIMPLE) return false;
    uint8_t info = head & 0x1F;
    if (info == 20)      *out = false;
    else if (info == 21) *out = true;
    else return false;
    if (_items) --_items;
    return true;
}

bool CborReader::read_string(const char** out, size_t* out_len) {
    if (_pos >= _len) return false;
    uint8_t head = _buf[_pos++];
    if ((head >> 5) != MT_STR) return false;
    uint8_t info = head & 0x1F;
    if (info >= 24) return false;
    if (_pos + info > _len) return false;
    *out = (const char*)(_buf + _pos);
    *out_len = info;
    _pos += info;
    if (_items) --_items;
    return true;
}

bool CborReader::skip() {
    if (_pos >= _len) return false;
    uint8_t head = _buf[_pos];
    uint8_t mt = head >> 5;
    if (mt == MT_UINT || mt == MT_SINT) { int64_t v; return read_int(&v); }
    if (mt == MT_STR)                   { const char* s; size_t l; return read_string(&s, &l); }
    if (mt == MT_SIMPLE) {
        uint8_t info = head & 0x1F;
        if (info == 20 || info == 21) { bool b; return read_bool(&b); }
        if (info == 27)               { double d; return read_float(&d); }
    }
    return false;
}

// ---------------------------------------------------------------------------
// DCP transceiver.

void DCP::set_wire_secret(const uint8_t* secret, size_t len) {
    if (len > sizeof(_wire_secret)) len = sizeof(_wire_secret);
    memcpy(_wire_secret, secret, len);
    _secret_len = len;
}

void DCP::poll() {
    while (_stream.available() > 0) {
        int b = _stream.read();
        if (b < 0) break;
        if (b == 0x00) {
            if (_rx_len > 0) {
                uint8_t decoded[MAX_FRAME_BYTES];
                size_t  decoded_len = 0;
                if (cobs_decode(_rx, _rx_len, decoded, &decoded_len) && decoded_len >= 2) {
                    size_t body_len = decoded_len - 2;
                    uint16_t expected = crc16_ccitt(decoded, body_len);
                    uint16_t got = ((uint16_t)decoded[body_len] << 8) | decoded[body_len + 1];
                    if (expected == got) {
                        // If wire signing is enabled, strip and verify the trailing HMAC.
                        if (_secret_len > 0) {
                            if (body_len >= HMAC_BYTES) {
                                size_t signed_len = body_len - HMAC_BYTES;
                                uint8_t expected_sig[HMAC_BYTES];
                                hmac_sha256_truncated(_wire_secret, _secret_len,
                                                      decoded, signed_len,
                                                      expected_sig, HMAC_BYTES);
                                if (ct_equal(expected_sig, decoded + signed_len, HMAC_BYTES)) {
                                    handle_frame(decoded, signed_len);
                                }
                            }
                        } else {
                            handle_frame(decoded, body_len);
                        }
                    }
                }
                _rx_len = 0;
            }
        } else if (_rx_len < MAX_FRAME_BYTES) {
            _rx[_rx_len++] = (uint8_t)b;
        } else {
            // overrun — discard and resync at next delimiter
            _rx_len = 0;
        }
    }
}

bool DCP::handle_frame(const uint8_t* frame, size_t len) {
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

bool DCP::send_frame(uint8_t kind, uint16_t seq, uint16_t iid,
                     const uint8_t* payload, size_t payload_len) {
    uint8_t frame[MAX_FRAME_BYTES];
    size_t reserved = HEADER_SIZE + payload_len + 2;
    if (_secret_len > 0) reserved += HMAC_BYTES;
    if (reserved > sizeof(frame)) return false;

    frame[0] = WIRE_VERSION;
    frame[1] = kind;
    frame[2] = (uint8_t)(seq >> 8); frame[3] = (uint8_t)seq;
    frame[4] = (uint8_t)(iid >> 8); frame[5] = (uint8_t)iid;
    memcpy(frame + HEADER_SIZE, payload, payload_len);
    size_t body_len = HEADER_SIZE + payload_len;

    if (_secret_len > 0) {
        hmac_sha256_truncated(_wire_secret, _secret_len,
                              frame, body_len,
                              frame + body_len, HMAC_BYTES);
        body_len += HMAC_BYTES;
    }

    uint16_t crc = crc16_ccitt(frame, body_len);
    frame[body_len]     = (uint8_t)(crc >> 8);
    frame[body_len + 1] = (uint8_t)crc;

    uint8_t out[MAX_FRAME_BYTES + 4];
    size_t out_len = cobs_encode(frame, body_len + 2, out);
    _stream.write(out, out_len);
    _stream.write((uint8_t)0x00);
    return true;
}

void DCP::send_error(uint16_t seq, uint16_t iid, Status status) {
    uint8_t buf[16];  // "status" key (8B map+keyhdr+chars) + uint value up to 9B headroom
    CborMap m(buf, sizeof(buf));
    m.begin();
    m.add_int("status", (int64_t)status);
    m.finish();
    send_frame(KIND_ERROR, seq, iid, buf, m.size());
}

bool DCP::send_event(const char* event_name, CborMap& payload) {
    payload.finish();
    return send_frame(KIND_EVENT, 0, intent_id(event_name), payload.data(), payload.size());
}

} // namespace dcp
