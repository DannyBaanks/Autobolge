"""
boot_analyzer.py - Analiza el boot code del baseline para entender cómo
se inicializa el puntero D y se establece la estructura de datos.
"""

ENCRYPT = "5z]&gqtyfr$(we4{WP)H-Zn,[%\\3dL+Q;>U!pJS72FhOA1CB6v^=I_0/8|jsb9m<.TVac`uY*MK'X~xDl}REokN:#?G\"i@"
CRAZY_TBL = [[1, 0, 0], [1, 0, 2], [2, 2, 1]]
POW10 = 59049


def crazy(a, b):
    res, p = 0, 1
    for _ in range(10):
        res += CRAZY_TBL[b % 3][a % 3] * p
        a, b, p = a // 3, b // 3, p * 3
    return res


def rotate(n):
    return (n % 3) * 19683 + (n // 3)


def main():
    with open('quine_research/baseline_quine.mal', 'r', encoding='latin1') as f:
        raw = f.read()
    clean = ''.join(c for c in raw if 33 <= ord(c) <= 126)

    mem = [0] * POW10
    for i, c in enumerate(clean):
        mem[i] = ord(c)
    for i in range(len(clean), POW10):
        mem[i] = crazy(mem[i - 1], mem[i - 2])

    a, c, d = 0, 0, 0
    d_history = []
    steps = 0
    mov_d_locations = []

    for _ in range(20000):
        val = mem[c]
        if val < 33 or val > 126:
            print(f"HALT at step {steps}: invalid mem[c={c}]={val}")
            break

        v = (val + c) % 94
        steps += 1

        if v == 4:    # jmp [d]
            c = mem[d]
        elif v == 5:  # out a
            pass
        elif v == 23: # in a
            a = 59048
        elif v == 39: # rotr [d]
            v_rot = rotate(mem[d])
            mem[d] = v_rot
            a = v_rot
        elif v == 40: # mov d, [d]
            d_before = d
            d = mem[d]
            d_history.append((steps, d_before, d, mem[d_before] if d_before < POW10 else -1))
            mov_d_locations.append((c, d_before, d))
        elif v == 62: # crz [d], a
            res = crazy(a, mem[d])
            mem[d] = res
            a = res
        elif v == 81: # end
            print(f"END at step {steps}")
            break

        if 33 <= mem[c] <= 126:
            mem[c] = ord(ENCRYPT[mem[c] - 33])
        c = 0 if c == POW10 - 1 else c + 1
        d = 0 if d == POW10 - 1 else d + 1

    print(f"\nTotal steps: {steps}")
    print(f"\nFirst 50 mov_d instructions:")
    for i, (pc, d_old, d_new) in enumerate(mov_d_locations[:50]):
        val_at_d_old = clean[d_old] if d_old < len(clean) else '?'
        print(f"  [{i:3d}] pc={pc:5d}  d: {d_old:5d} -> {d_new:5d}  (M[{d_old}]={repr(val_at_d_old)})")

    print(f"\nUnique D values visited (first 200 mov_d):")
    unique_d = sorted(set(d_new for _, _, d_new in mov_d_locations[:200]))
    print(f"  Count: {len(unique_d)}")
    print(f"  Range: {unique_d[0]} .. {unique_d[-1]}")
    print(f"  First 50: {unique_d[:50]}")
    print(f"  Last 50:  {unique_d[-50:]}")

    # Identify the "main loop" D values (most frequent)
    from collections import Counter
    d_counter = Counter(d_new for _, _, d_new in mov_d_locations)
    print(f"\nTop 20 most frequent d targets:")
    for d_val, cnt in d_counter.most_common(20):
        print(f"  d={d_val:5d}: {cnt:6d} times")


if __name__ == '__main__':
    main()