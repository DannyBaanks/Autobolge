/* frontier_indep.c - Independent exhaustive Malbolge frontier scanner.
 *
 * Written from the 1998 Malbolge specification, NOT derived from Autobolge's
 * vm.zig / classic.py, so it can act as an external judge of their results.
 * Semantics = Autobolge CURRENT epoch "autobolge-classic-dense-input-underflow/v1"
 * (toolkit engine.zig): dense 59049-cell tape filled by the crazy recurrence,
 * opcode = ([c]+c) % 94, opcodes outside the 8 valid ones are NOP, encryption
 * only when the cell is in 33..126, reading input with empty stdin terminates
 * (INPUT_UNDERFLOW), output = a % 256.
 *
 * Speed trick (does not change semantics): for a fixed program length L the
 * tape tail m[L..] depends only on (m[L-2], m[L-1]); the tail is computed once
 * per pair and every write made by a run is logged and undone afterwards.
 *
 * Enumerates all 8^L programs of length L whose every cell decodes to a valid
 * instruction (same candidate set as Materialization.build_catalog).
 *
 * Usage: frontier_indep <L> <max_steps> <target_hex|-> [threads]
 * stdout: one JSON object (evidence). Exit 0.
 */
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define N 59049
#define MAXL 16
#define MAXHITS 2000
#define UNDO_CAP 16384

static const char *XLAT2 =
    "5z]&gqtyfr$(we4{WP)H-Zn,[%\\3dL+Q;>U!pJS72FhOA1CB6v^=I_0/8|jsb9m<.TVac`uY*MK'X~xDl}REokN:#?G\"i@";
static const int VALID[8] = {4, 5, 23, 39, 40, 62, 68, 81};

static unsigned crz(unsigned a, unsigned d) {
    static const unsigned t[3][3] = {{1, 0, 0}, {1, 0, 2}, {2, 2, 1}}; /* t[d_trit][a_trit] */
    unsigned r = 0, p = 1;
    for (int i = 0; i < 10; i++) { r += t[d % 3][a % 3] * p; a /= 3; d /= 3; p *= 3; }
    return r;
}

static int L, NT;
static long long MAXSTEPS;
static unsigned char TGT[64];
static int TL = -1;
static unsigned CH[MAXL][8];

typedef struct {
    int tid;
    unsigned m[N];
    unsigned ui[UNDO_CAP], uv[UNDO_CAP];
    long long total, hits, terminated, underflow, running;
    char hitprog[MAXHITS][MAXL + 1];
    int nhit;
    /* first (lowest enumeration index within this thread) witness per exact output */
    char *w1;              /* 256 * (MAXL+1) */
    char *w2;              /* 65536 * (MAXL+1) */
    unsigned char *b3;     /* 2^24 bitmap of exact 3-byte outputs */
} Worker;

static void *work(void *arg) {
    Worker *w = (Worker *)arg;
    long long inner = 1;
    for (int i = 0; i < L - 2; i++) inner *= 8;
    for (int pair = w->tid; pair < 64; pair += NT) {
        int dA = pair / 8, dB = pair % 8; /* digits for positions L-2, L-1 */
        w->m[L - 2] = CH[L - 2][dA];
        w->m[L - 1] = CH[L - 1][dB];
        for (int i = L; i < N; i++) w->m[i] = crz(w->m[i - 1], w->m[i - 2]);
        for (long long idx = 0; idx < inner; idx++) {
            long long t = idx;
            for (int i = 0; i < L - 2; i++) { w->m[i] = CH[i][t % 8]; t /= 8; }
            w->m[L - 2] = CH[L - 2][dA];
            w->m[L - 1] = CH[L - 1][dB];
            char prog[MAXL + 1];
            for (int i = 0; i < L; i++) prog[i] = (char)w->m[i];
            prog[L] = 0;
            unsigned *m = w->m;
            int nu = 0;
            unsigned a = 0, c = 0, d = 0;
            long long s = 0;
            unsigned char out[64];
            int on = 0, over = 0, reason = 0; /* 0 running, 1 halt, 2 underflow */
            while (s < MAXSTEPS) {
                int op = (int)((m[c] + c) % 94);
                s++;
                int h = 0;
                switch (op) {
                case 4: c = m[d]; break;
                case 5: if (on < 64) out[on++] = (unsigned char)(a % 256); else over = 1; break;
                case 23: h = 1; reason = 2; break;
                case 39: w->ui[nu] = d; w->uv[nu++] = m[d]; a = m[d] = m[d] / 3 + (m[d] % 3) * 19683; break;
                case 40: d = m[d]; break;
                case 62: w->ui[nu] = d; w->uv[nu++] = m[d]; a = m[d] = crz(a, m[d]); break;
                case 81: h = 1; reason = 1; break;
                default: break;
                }
                if (h) break;
                if (m[c] >= 33 && m[c] <= 126) { w->ui[nu] = c; w->uv[nu++] = m[c]; m[c] = (unsigned)XLAT2[m[c] - 33]; }
                c = (c + 1) % N;
                d = (d + 1) % N;
            }
            while (nu > 0) { nu--; m[w->ui[nu]] = w->uv[nu]; }
            w->total++;
            if (reason == 1) w->terminated++; else if (reason == 2) w->underflow++; else w->running++;
            if (over) continue;
            if (TL >= 0 && on == TL && memcmp(out, TGT, (size_t)TL) == 0) {
                w->hits++;
                if (w->nhit < MAXHITS) strcpy(w->hitprog[w->nhit++], prog);
            }
            if (on == 1) { char *slot = w->w1 + out[0] * (MAXL + 1); if (!slot[0]) strcpy(slot, prog); }
            if (on == 2) { char *slot = w->w2 + (out[0] * 256 + out[1]) * (MAXL + 1); if (!slot[0]) strcpy(slot, prog); }
            if (on == 3) { unsigned k = ((unsigned)out[0] << 16) | ((unsigned)out[1] << 8) | out[2]; w->b3[k >> 3] |= (unsigned char)(1u << (k & 7)); }
        }
    }
    return NULL;
}

static void json_str(const char *s) {
    putchar('"');
    for (; *s; s++) {
        if (*s == '"' || *s == '\\') { putchar('\\'); putchar(*s); }
        else putchar(*s);
    }
    putchar('"');
}

int main(int argc, char **argv) {
    if (argc < 4) { fprintf(stderr, "usage: %s L max_steps target_hex|- [threads]\n", argv[0]); return 2; }
    L = atoi(argv[1]);
    MAXSTEPS = atoll(argv[2]);
    if (L < 2 || L > MAXL) { fprintf(stderr, "L must be 2..%d\n", MAXL); return 2; }
    if (MAXSTEPS < 1 || MAXSTEPS * 2 > UNDO_CAP) { fprintf(stderr, "max_steps must be 1..%d (undo log)\n", UNDO_CAP / 2); return 2; }
    if (strcmp(argv[3], "-") != 0) {
        size_t hl = strlen(argv[3]);
        TL = (int)(hl / 2);
        for (int i = 0; i < TL; i++) { unsigned v; sscanf(argv[3] + 2 * i, "%2x", &v); TGT[i] = (unsigned char)v; }
    }
    NT = argc > 4 ? atoi(argv[4]) : 1;
    if (NT < 1) NT = 1;
    if (NT > 64) NT = 64;
    for (int i = 0; i < L; i++)
        for (int k = 0; k < 8; k++) {
            int ch = 33 + (((VALID[k] - 33 - i) % 94) + 94) % 94;
            CH[i][k] = (unsigned)ch;
        }
    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    Worker **ws = calloc((size_t)NT, sizeof(Worker *));
    pthread_t *th = calloc((size_t)NT, sizeof(pthread_t));
    for (int i = 0; i < NT; i++) {
        ws[i] = calloc(1, sizeof(Worker));
        ws[i]->tid = i;
        ws[i]->w1 = calloc(256, MAXL + 1);
        ws[i]->w2 = calloc(65536, MAXL + 1);
        ws[i]->b3 = calloc(1u << 21, 1);
        pthread_create(&th[i], NULL, work, ws[i]);
    }
    for (int i = 0; i < NT; i++) pthread_join(th[i], NULL);
    clock_gettime(CLOCK_MONOTONIC, &t1);
    double el = (double)(t1.tv_sec - t0.tv_sec) + (double)(t1.tv_nsec - t0.tv_nsec) / 1e9;

    long long total = 0, hits = 0, term = 0, uf = 0, run = 0;
    for (int i = 0; i < NT; i++) { total += ws[i]->total; hits += ws[i]->hits; term += ws[i]->terminated; uf += ws[i]->underflow; run += ws[i]->running; }
    long long n3 = 0;
    for (unsigned k = 0; k < (1u << 21); k++) {
        unsigned char b = 0;
        for (int i = 0; i < NT; i++) b |= ws[i]->b3[k];
        n3 += __builtin_popcount(b);
    }
    printf("{\"tool\":\"tools/indep_scan/frontier_indep.c\",\"semantic_epoch\":\"autobolge-classic-dense-input-underflow/v1\",");
    printf("\"length\":%d,\"max_steps\":%lld,\"input\":\"\",\"threads\":%d,", L, MAXSTEPS, NT);
    printf("\"target_hex\":\"%s\",", TL >= 0 ? argv[3] : "");
    printf("\"total_programs\":%lld,\"stop_reasons\":{\"TERMINATED\":%lld,\"INPUT_UNDERFLOW\":%lld,\"RUNNING\":%lld},", total, term, uf, run);
    printf("\"hits\":%lld,\"negative\":%s,\"hit_programs\":[", hits, (TL >= 0 && hits == 0) ? "true" : "false");
    int first = 1;
    for (int i = 0; i < NT; i++)
        for (int j = 0; j < ws[i]->nhit; j++) { if (!first) putchar(','); first = 0; json_str(ws[i]->hitprog[j]); }
    printf("],\"elapsed_s\":%.3f,", el);
    /* exact-output witnesses: deterministic choice = lexicographically smallest program among thread witnesses */
    long long n1 = 0, n2 = 0;
    printf("\"one_byte_outputs\":{");
    first = 1;
    for (int o = 0; o < 256; o++) {
        const char *best = NULL;
        for (int i = 0; i < NT; i++) { const char *s = ws[i]->w1 + o * (MAXL + 1); if (s[0] && (!best || strcmp(s, best) < 0)) best = s; }
        if (best) { if (!first) putchar(','); first = 0; printf("\"%02x\":", o); json_str(best); n1++; }
    }
    printf("},\"two_byte_outputs\":{");
    first = 1;
    for (int o = 0; o < 65536; o++) {
        const char *best = NULL;
        for (int i = 0; i < NT; i++) { const char *s = ws[i]->w2 + o * (MAXL + 1); if (s[0] && (!best || strcmp(s, best) < 0)) best = s; }
        if (best) { if (!first) putchar(','); first = 0; printf("\"%04x\":", o); json_str(best); n2++; }
    }
    printf("},\"distinct_one_byte_outputs\":%lld,\"distinct_two_byte_outputs\":%lld,\"distinct_three_byte_outputs\":%lld}\n", n1, n2, n3);
    return 0;
}
