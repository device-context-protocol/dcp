// SHA-256 and HMAC-SHA256 — small, self-contained.
//
// Provided so DCP firmware does not depend on mbedtls or ESP-IDF specifics,
// and remains portable across MCU vendors. About 1 KB of code, ~200 bytes of
// stack per HMAC invocation.

#ifndef DCP_CRYPTO_H
#define DCP_CRYPTO_H

#include <stdint.h>
#include <stddef.h>

namespace dcp {

struct Sha256Ctx {
    uint32_t state[8];
    uint32_t length_hi;
    uint32_t length_lo;
    uint32_t buflen;
    uint8_t  buf[64];
};

void sha256_init(Sha256Ctx& ctx);
void sha256_update(Sha256Ctx& ctx, const uint8_t* data, size_t len);
void sha256_final(Sha256Ctx& ctx, uint8_t out[32]);

// HMAC-SHA256. Caller supplies key (any length) and message. Writes 32 bytes
// of output. ``hmac_sha256_truncated`` writes only the first ``out_len``
// bytes — DCP wire signing uses 16.
void hmac_sha256(const uint8_t* key, size_t key_len,
                 const uint8_t* msg, size_t msg_len,
                 uint8_t out[32]);

void hmac_sha256_truncated(const uint8_t* key, size_t key_len,
                           const uint8_t* msg, size_t msg_len,
                           uint8_t* out, size_t out_len);

// Constant-time equality check.
bool ct_equal(const uint8_t* a, const uint8_t* b, size_t len);

} // namespace dcp

#endif // DCP_CRYPTO_H
