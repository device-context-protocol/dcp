// SHA-256 and HMAC-SHA256. Small, public-domain-equivalent (MIT) implementation.
// Reviewed against FIPS 180-4 and RFC 2104 test vectors before shipping.

#include "DCPCrypto.h"
#include <string.h>

namespace dcp {

namespace {

constexpr uint32_t K[64] = {
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
};

inline uint32_t rotr(uint32_t v, int n) { return (v >> n) | (v << (32 - n)); }

void compress(uint32_t state[8], const uint8_t block[64]) {
    uint32_t w[64];
    for (int i = 0; i < 16; ++i) {
        w[i] = ((uint32_t)block[i * 4] << 24) | ((uint32_t)block[i * 4 + 1] << 16)
             | ((uint32_t)block[i * 4 + 2] << 8) | (uint32_t)block[i * 4 + 3];
    }
    for (int i = 16; i < 64; ++i) {
        uint32_t s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
        uint32_t s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
        w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }
    uint32_t a = state[0], b = state[1], c = state[2], d = state[3];
    uint32_t e = state[4], f = state[5], g = state[6], h = state[7];
    for (int i = 0; i < 64; ++i) {
        uint32_t S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
        uint32_t ch = (e & f) ^ ((~e) & g);
        uint32_t t1 = h + S1 + ch + K[i] + w[i];
        uint32_t S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
        uint32_t mj = (a & b) ^ (a & c) ^ (b & c);
        uint32_t t2 = S0 + mj;
        h = g; g = f; f = e; e = d + t1;
        d = c; c = b; b = a; a = t1 + t2;
    }
    state[0] += a; state[1] += b; state[2] += c; state[3] += d;
    state[4] += e; state[5] += f; state[6] += g; state[7] += h;
}

} // anonymous namespace

void sha256_init(Sha256Ctx& ctx) {
    ctx.state[0] = 0x6a09e667; ctx.state[1] = 0xbb67ae85;
    ctx.state[2] = 0x3c6ef372; ctx.state[3] = 0xa54ff53a;
    ctx.state[4] = 0x510e527f; ctx.state[5] = 0x9b05688c;
    ctx.state[6] = 0x1f83d9ab; ctx.state[7] = 0x5be0cd19;
    ctx.length_hi = 0;
    ctx.length_lo = 0;
    ctx.buflen = 0;
}

void sha256_update(Sha256Ctx& ctx, const uint8_t* data, size_t len) {
    // Update 64-bit length in bits, big-endian split into (hi, lo).
    uint32_t add_lo = (uint32_t)(len << 3);
    uint32_t add_hi = (uint32_t)(len >> 29);
    ctx.length_hi += add_hi;
    if ((ctx.length_lo + add_lo) < ctx.length_lo) ctx.length_hi += 1;
    ctx.length_lo += add_lo;

    while (len > 0) {
        size_t fill = 64 - ctx.buflen;
        size_t take = len < fill ? len : fill;
        memcpy(ctx.buf + ctx.buflen, data, take);
        ctx.buflen += (uint32_t)take;
        data += take;
        len  -= take;
        if (ctx.buflen == 64) {
            compress(ctx.state, ctx.buf);
            ctx.buflen = 0;
        }
    }
}

void sha256_final(Sha256Ctx& ctx, uint8_t out[32]) {
    ctx.buf[ctx.buflen++] = 0x80;
    if (ctx.buflen > 56) {
        memset(ctx.buf + ctx.buflen, 0, 64 - ctx.buflen);
        compress(ctx.state, ctx.buf);
        ctx.buflen = 0;
    }
    memset(ctx.buf + ctx.buflen, 0, 56 - ctx.buflen);
    uint32_t hi = ctx.length_hi;
    uint32_t lo = ctx.length_lo;
    ctx.buf[56] = (uint8_t)(hi >> 24); ctx.buf[57] = (uint8_t)(hi >> 16);
    ctx.buf[58] = (uint8_t)(hi >> 8);  ctx.buf[59] = (uint8_t)hi;
    ctx.buf[60] = (uint8_t)(lo >> 24); ctx.buf[61] = (uint8_t)(lo >> 16);
    ctx.buf[62] = (uint8_t)(lo >> 8);  ctx.buf[63] = (uint8_t)lo;
    compress(ctx.state, ctx.buf);
    for (int i = 0; i < 8; ++i) {
        out[i * 4]     = (uint8_t)(ctx.state[i] >> 24);
        out[i * 4 + 1] = (uint8_t)(ctx.state[i] >> 16);
        out[i * 4 + 2] = (uint8_t)(ctx.state[i] >> 8);
        out[i * 4 + 3] = (uint8_t)ctx.state[i];
    }
}

void hmac_sha256(const uint8_t* key, size_t key_len,
                 const uint8_t* msg, size_t msg_len,
                 uint8_t out[32]) {
    uint8_t k[64] = {0};
    if (key_len > 64) {
        Sha256Ctx tmp;
        sha256_init(tmp);
        sha256_update(tmp, key, key_len);
        sha256_final(tmp, k);
    } else {
        memcpy(k, key, key_len);
    }
    uint8_t ipad[64], opad[64];
    for (int i = 0; i < 64; ++i) {
        ipad[i] = k[i] ^ 0x36;
        opad[i] = k[i] ^ 0x5c;
    }
    uint8_t inner[32];
    Sha256Ctx c1;
    sha256_init(c1);
    sha256_update(c1, ipad, 64);
    sha256_update(c1, msg, msg_len);
    sha256_final(c1, inner);

    Sha256Ctx c2;
    sha256_init(c2);
    sha256_update(c2, opad, 64);
    sha256_update(c2, inner, 32);
    sha256_final(c2, out);
}

void hmac_sha256_truncated(const uint8_t* key, size_t key_len,
                           const uint8_t* msg, size_t msg_len,
                           uint8_t* out, size_t out_len) {
    uint8_t full[32];
    hmac_sha256(key, key_len, msg, msg_len, full);
    if (out_len > 32) out_len = 32;
    memcpy(out, full, out_len);
}

bool ct_equal(const uint8_t* a, const uint8_t* b, size_t len) {
    uint8_t r = 0;
    for (size_t i = 0; i < len; ++i) r |= (uint8_t)(a[i] ^ b[i]);
    return r == 0;
}

} // namespace dcp
