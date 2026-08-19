import hashlib
import time
from malbolge.malbolge import eval as eval_classic

def inspect_baseline():
    with open('quine_research/baseline_quine.mal', 'rb') as f:
        raw = f.read()

    text = raw.decode('latin1')
    clean = ''.join(c for c in text if 33 <= ord(c) <= 126)
    
    sha_raw = hashlib.sha256(raw).hexdigest()
    sha_clean = hashlib.sha256(clean.encode('latin1')).hexdigest()
    
    lines = raw.split(b'\n')
    n_newlines = raw.count(b'\n')
    n_cr = raw.count(b'\r')
    
    print("=== BASELINE QUINE INSPECTION ===")
    print(f"Raw file size:        {len(raw)} bytes")
    print(f"Printable chars:      {len(clean)} chars")
    print(f"Lines count:          {len(lines)}")
    print(f"Newlines (0x0A):      {n_newlines}")
    print(f"Carriage returns:     {n_cr}")
    print(f"Line lengths (0..5):  {[len(l) for l in lines[:5]]}")
    print(f"SHA-256 (raw):        {sha_raw}")
    print(f"SHA-256 (clean):      {sha_clean}")
    
    # Check structure: 29516 + 29516
    code_part = clean[:29516]
    data_part = clean[29516:59032]
    print(f"\n=== STRUCTURAL DIVISION ===")
    print(f"Code section length:  {len(code_part)}")
    print(f"Data section length:  {len(data_part)}")
    print(f"Code == Data:         {code_part == data_part}")
    print(f"Code len % 94:        {len(code_part) % 94}")
    print(f"Remaining in 59049:   {59049 - len(clean)}")
    
    print("\n=== EXECUTING BASELINE QUINE ===")
    t0 = time.time()
    out = eval_classic(text, input='', eof='stop')
    elapsed = time.time() - t0
    
    out_bytes = out.encode('latin1')
    sha_out = hashlib.sha256(out_bytes).hexdigest()
    
    print(f"Execution time:       {elapsed:.3f} s")
    print(f"Output length:        {len(out)} chars ({len(out_bytes)} bytes)")
    print(f"Output SHA-256:       {sha_out}")
    print(f"Output == Raw file:   {out_bytes == raw}")
    print(f"Output == Clean:      {out == clean}")

if __name__ == '__main__':
    inspect_baseline()
