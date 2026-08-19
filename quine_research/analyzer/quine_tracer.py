"""
quine_tracer.py - Analizador estructural y tracer detallado para la Quine de Malbolge.

Replica la semántica exacta del evaluador de referencia (malbolge.malbolge.eval)
para trazar paso a paso la quine baseline de Matthias Lutter, registrando:
  - PCs ejecutados y frecuencia
  - Direcciones D leidas/escritas y frecuencia
  - Opcodes ejecutados y frecuencia
  - Posiciones de memoria encriptadas
  - Output generado (paso, char, valores de A/C/D, mem[D])
  - Estructura de bucles

Uso:
    python quine_tracer.py [max_steps] [sample_interval]

Salida:
    quine_research/evidence/baseline_analysis.json
"""

import sys
import time
import json
import hashlib
import collections

ENCRYPT = "5z]&gqtyfr$(we4{WP)H-Zn,[%\\3dL+Q;>U!pJS72FhOA1CB6v^=I_0/8|jsb9m<.TVac`uY*MK'X~xDl}REokN:#?G\"i@"
CRAZY_TBL = [
    [1, 0, 0],
    [1, 0, 2],
    [2, 2, 1]
]
POW10 = 59049
EOF_A = 59048


def crazy(a, b):
    res = 0
    p = 1
    for _ in range(10):
        res += CRAZY_TBL[b % 3][a % 3] * p
        a //= 3
        b //= 3
        p *= 3
    return res


def rotate(n):
    return (n % 3) * 19683 + (n // 3)


class QuineAnalyzer:
    def __init__(self, raw_source: str):
        self.raw_source = raw_source
        self.clean_source = ''.join(c for c in raw_source if 33 <= ord(c) <= 126)
        self.src_len = len(self.clean_source)
        assert self.src_len == 59032, f"Expected 59032, got {self.src_len}"

        # Memory load (positions 0..src_len-1)
        self.mem = [0] * POW10
        for i, c in enumerate(self.clean_source):
            self.mem[i] = ord(c)
        # Crazy fill (positions src_len..POW10-1)
        for i in range(self.src_len, POW10):
            self.mem[i] = crazy(self.mem[i - 1], self.mem[i - 2])
        self.initial_mem = list(self.mem)

        # Registers
        self.a = 0
        self.c = 0
        self.d = 0

        # Counters
        self.step_count = 0
        self.op_counts = collections.Counter()

        # Access maps
        self.pc_executed = collections.Counter()
        self.d_reads = collections.Counter()
        self.d_writes = collections.Counter()
        self.mem_encrypted = collections.Counter()

        # Output tracking
        self.output_events = []
        self.output_first_n = 1000

    def step(self):
        c_curr = self.c
        val = self.mem[c_curr]

        if val < 33 or val > 126:
            return False, "halt_invalid_mem"

        v = (val + c_curr) % 94
        self.pc_executed[c_curr] += 1
        self.step_count += 1

        # ---- Opcode dispatch (matches reference eval exactly) ----
        if v == 4:  # jmp [d]
            self.op_counts['jmp'] += 1
            self.d_reads[self.d] += 1
            self.c = self.mem[self.d]
        elif v == 5:  # out a
            self.op_counts['out'] += 1
            ch = chr(self.a % 256)
            self._record_output(ch)
        elif v == 23:  # in a
            self.op_counts['in'] += 1
            self.a = EOF_A
        elif v == 39:  # rotr [d]; mov a, [d]
            self.op_counts['rotr'] += 1
            self.d_reads[self.d] += 1
            v_rot = rotate(self.mem[self.d])
            self.mem[self.d] = v_rot
            self.d_writes[self.d] += 1
            self.a = v_rot
        elif v == 40:  # mov d, [d]
            self.op_counts['mov_d'] += 1
            self.d_reads[self.d] += 1
            self.d = self.mem[self.d]
        elif v == 62:  # crz [d], a; mov a, [d]
            self.op_counts['crz'] += 1
            self.d_reads[self.d] += 1
            res = crazy(self.a, self.mem[self.d])
            self.mem[self.d] = res
            self.d_writes[self.d] += 1
            self.a = res
        elif v == 81:  # end
            self.op_counts['end'] += 1
            return False, "end_opcode"
        else:
            # nop (v == 68 or any other value)
            self.op_counts['nop'] += 1

        # ---- Encrypt mem[c] (POST-execution c, which may have been changed by jmp) ----
        if 33 <= self.mem[self.c] <= 126:
            self.mem[self.c] = ord(ENCRYPT[self.mem[self.c] - 33])
            self.mem_encrypted[self.c] += 1

        # ---- Advance c, d ----
        self.c = 0 if self.c == POW10 - 1 else self.c + 1
        self.d = 0 if self.d == POW10 - 1 else self.d + 1

        return True, None

    def _record_output(self, ch):
        evt = {
            "step": self.step_count,
            "char": ch,
            "ord": ord(ch),
            "a": self.a,
            "c_pre": (self.c - 1) % POW10,  # the pc that emitted
            "d": self.d,                    # d will advance AFTER this step
        }
        if len(self.output_events) < self.output_first_n:
            self.output_events.append(evt)

    def run(self, max_steps=100_000_000, sample_interval=5_000_000):
        t0 = time.time()
        print(f"[*] Tracing baseline quine (clean_len={self.src_len}, max_steps={max_steps})...")

        while self.step_count < max_steps:
            cont, reason = self.step()
            if not cont:
                print(f"[*] Halt at step {self.step_count:,}: {reason}")
                return reason
            if self.step_count % sample_interval == 0:
                elapsed = time.time() - t0
                rate = self.step_count / max(0.001, elapsed)
                print(f"  [step {self.step_count:,}] rate={rate:,.0f} steps/s, c={self.c}, d={self.d}")
        return "max_steps"

    def build_report(self, halt_reason, elapsed_s):
        return {
            "baseline": {
                "raw_size": len(self.raw_source),
                "clean_size": self.src_len,
                "code_region": [0, 29515],
                "data_region": [29516, 59031],
                "code_equals_data": self.clean_source[:29516] == self.clean_source[29516:59032],
                "remaining_in_mem": POW10 - self.src_len,
                "sha256_clean": hashlib.sha256(self.clean_source.encode('latin1')).hexdigest(),
            },
            "execution": {
                "halt_reason": halt_reason,
                "elapsed_s": elapsed_s,
                "total_steps": self.step_count,
                "opcode_counts": dict(self.op_counts),
            },
            "structural": {
                "unique_pcs_executed": len(self.pc_executed),
                "pc_min": min(self.pc_executed.keys()) if self.pc_executed else None,
                "pc_max": max(self.pc_executed.keys()) if self.pc_executed else None,
                "pc_in_code_region": sum(cnt for pc, cnt in self.pc_executed.items() if pc <= 29515),
                "pc_in_data_region": sum(cnt for pc, cnt in self.pc_executed.items() if 29516 <= pc <= 59031),
                "pc_in_fill_region": sum(cnt for pc, cnt in self.pc_executed.items() if pc > 59031),
                "top_20_pcs": self.pc_executed.most_common(20),
                "unique_d_reads": len(self.d_reads),
                "d_read_min": min(self.d_reads.keys()) if self.d_reads else None,
                "d_read_max": max(self.d_reads.keys()) if self.d_reads else None,
                "d_read_in_code_region": sum(cnt for d, cnt in self.d_reads.items() if d <= 29515),
                "d_read_in_data_region": sum(cnt for d, cnt in self.d_reads.items() if 29516 <= d <= 59031),
                "d_read_in_fill_region": sum(cnt for d, cnt in self.d_reads.items() if d > 59031),
                "top_20_d_reads": self.d_reads.most_common(20),
                "unique_d_writes": len(self.d_writes),
                "d_write_min": min(self.d_writes.keys()) if self.d_writes else None,
                "d_write_max": max(self.d_writes.keys()) if self.d_writes else None,
                "top_20_d_writes": self.d_writes.most_common(20),
                "unique_encrypted": len(self.mem_encrypted),
                "encrypted_in_code_region": sum(cnt for m, cnt in self.mem_encrypted.items() if m <= 29515),
                "encrypted_in_data_region": sum(cnt for m, cnt in self.mem_encrypted.items() if 29516 <= m <= 59031),
                "encrypted_in_fill_region": sum(cnt for m, cnt in self.mem_encrypted.items() if m > 59031),
            },
            "output_samples": {
                "first_n": self.output_events[:50],
                "first_n_len": min(50, len(self.output_events)),
            }
        }


def verify_output(raw_source):
    """Full re-run with output capture to verify the quine property."""
    clean = ''.join(c for c in raw_source if 33 <= ord(c) <= 126)
    mem = [0] * POW10
    for i, c in enumerate(clean):
        mem[i] = ord(c)
    for i in range(len(clean), POW10):
        mem[i] = crazy(mem[i - 1], mem[i - 2])

    a, c, d = 0, 0, 0
    out = []
    steps = 0
    while True:
        val = mem[c]
        if val < 33 or val > 126:
            break
        v = (val + c) % 94
        steps += 1
        if v == 4:
            c = mem[d]
        elif v == 5:
            out.append(chr(a % 256))
        elif v == 23:
            a = EOF_A
        elif v == 39:
            v_rot = rotate(mem[d])
            mem[d] = v_rot
            a = v_rot
        elif v == 40:
            d = mem[d]
        elif v == 62:
            res = crazy(a, mem[d])
            mem[d] = res
            a = res
        elif v == 81:
            break
        if 33 <= mem[c] <= 126:
            mem[c] = ord(ENCRYPT[mem[c] - 33])
        c = 0 if c == POW10 - 1 else c + 1
        d = 0 if d == POW10 - 1 else d + 1

    return ''.join(out), steps


def main():
    max_steps = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000_000
    sample_interval = int(sys.argv[2]) if len(sys.argv) > 2 else 5_000_000

    with open('quine_research/baseline_quine.mal', 'r', encoding='latin1') as f:
        raw = f.read()

    analyzer = QuineAnalyzer(raw)
    t0 = time.time()
    halt_reason = analyzer.run(max_steps=max_steps, sample_interval=sample_interval)
    elapsed = time.time() - t0

    report = analyzer.build_report(halt_reason, elapsed)
    out_path = 'quine_research/evidence/baseline_analysis.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    print(f"\n[*] Report saved to {out_path}")

    # Verification pass
    print("\n[*] Verification pass (re-run with full output capture)...")
    output_str, total_steps = verify_output(raw)
    print(f"[*] Full output length: {len(output_str)} chars")
    print(f"[*] Output == raw file: {output_str == raw}")
    print(f"[*] Output == clean:    {output_str == analyzer.clean_source}")
    print(f"[*] Total steps:        {total_steps:,}")
    if output_str == raw:
        print("[*] QUINE PROPERTY VERIFIED")
    else:
        print("[!] QUINE PROPERTY FAILED")
        # Show first diff
        for i in range(min(len(output_str), len(raw))):
            if output_str[i] != raw[i]:
                print(f"  First diff at byte {i}: out={output_str[i]!r} raw={raw[i]!r}")
                break


if __name__ == '__main__':
    main()
