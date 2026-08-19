"""
loop_analyzer.py - Analiza el bucle de impresión de la Quine:
- Traza qué direcciones de memoria se leen para producir cada caracter.
- Verifica si el puntero lee la región DATA (29516..59031) dos veces.
- Analiza cómo y cuándo se emiten los saltos de línea (0x0A / 10).
- Determina si la región DATA es leída en su totalidad (100% de los 29,516 caracteres).
"""

import hashlib
import json
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

def analyze_printing_loop():
    with open('quine_research/baseline_quine.mal', 'r', encoding='latin1') as f:
        raw = f.read()
    clean = ''.join(c for c in raw if 33 <= ord(c) <= 126)
    
    mem = [0] * POW10
    for i, c in enumerate(clean):
        mem[i] = ord(c)
    for i in range(len(clean), POW10):
        mem[i] = crazy(mem[i - 1], mem[i - 2])
        
    a, c, d = 0, 0, 0
    steps = 0
    
    output_chars = []
    output_steps = []
    output_line_counts = []
    
    # We will record memory reads performed between outputs
    reads_between_outputs = set()
    all_data_reads = collections.Counter()
    
    char_index = 0
    newline_count = 0
    printable_count = 0
    
    # Track passes over the source
    pass1_data_indices = []
    pass2_data_indices = []
    
    print("[*] Running detailed loop tracer...")
    while True:
        val = mem[c]
        if val < 33 or val > 126:
            break
        v = (val + c) % 94
        steps += 1
        
        if v == 4: # jmp [d]
            reads_between_outputs.add(d)
            c = mem[d]
        elif v == 5: # out a
            ch = chr(a % 256)
            output_chars.append(ch)
            output_steps.append(steps)
            
            if ch == '\n':
                newline_count += 1
            else:
                printable_count += 1
                if printable_count <= 29516:
                    pass1_data_indices.append(list(reads_between_outputs))
                else:
                    pass2_data_indices.append(list(reads_between_outputs))
                    
            reads_between_outputs.clear()
            
        elif v == 23:
            a = EOF_A
        elif v == 39: # rotr [d]
            reads_between_outputs.add(d)
            if 29516 <= d <= 59031:
                all_data_reads[d] += 1
            v_rot = rotate(mem[d])
            mem[d] = v_rot
            a = v_rot
        elif v == 40: # mov d, [d]
            reads_between_outputs.add(d)
            if 29516 <= d <= 59031:
                all_data_reads[d] += 1
            d = mem[d]
        elif v == 62: # crz [d], a
            reads_between_outputs.add(d)
            if 29516 <= d <= 59031:
                all_data_reads[d] += 1
            res = crazy(a, mem[d])
            mem[d] = res
            a = res
        elif v == 81: # end
            break
            
        if 33 <= mem[c] <= 126:
            mem[c] = ord(ENCRYPT[mem[c] - 33])
            
        c = 0 if c == POW10 - 1 else c + 1
        d = 0 if d == POW10 - 1 else d + 1
        
    print(f"[*] Finished loop trace. Steps: {steps:,}")
    print(f"[*] Total output length: {len(output_chars):,}")
    print(f"[*] Printable chars: {printable_count:,} (expected 59,032)")
    print(f"[*] Newline chars: {newline_count:,} (expected 820)")
    print(f"[*] Unique DATA cells read: {len(all_data_reads):,} / 29,516")
    
    # Are all 29,516 data cells read?
    unread_data = [i for i in range(29516, 59032) if i not in all_data_reads]
    print(f"[*] Unread DATA cells count: {len(unread_data)}")
    if unread_data:
        print(f"[*] Unread data sample: {unread_data[:10]}")
        
    # Check intervals between outputs
    intervals = [output_steps[i] - output_steps[i-1] for i in range(1, min(100, len(output_steps)))]
    print(f"[*] First 20 step intervals between outputs: {intervals[:20]}")
    
    # Analysis result dictionary
    analysis = {
        "total_steps": steps,
        "output_len": len(output_chars),
        "printable_count": printable_count,
        "newline_count": newline_count,
        "unique_data_cells_read": len(all_data_reads),
        "total_data_cells": 29516,
        "all_data_read_fraction": len(all_data_reads) / 29516.0,
        "unread_data_count": len(unread_data),
        "unread_data_cells": unread_data,
        "data_read_frequencies": {
            "min": min(all_data_reads.values()) if all_data_reads else 0,
            "max": max(all_data_reads.values()) if all_data_reads else 0,
            "mean": sum(all_data_reads.values()) / max(1, len(all_data_reads)),
        }
    }
    
    with open('quine_research/evidence/loop_analysis.json', 'w') as f:
        json.dump(analysis, f, indent=2)
    print("[*] Saved loop analysis to quine_research/evidence/loop_analysis.json")

if __name__ == '__main__':
    analyze_printing_loop()
