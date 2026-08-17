#!/usr/bin/env python3
"""
CLI for Malbolge Translator.

Usage:
    malbolge-translate "Hello world" --execute
    malbolge-translate input.txt --output-dir out --execute
    malbolge-translate --quijote --output-dir quijote_output
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .translator import MalbolgeTranslator
from .lexicon import Lexicon

try:
    from .render_session import render_malbolge_session
    RENDER_AVAILABLE = True
except ImportError:
    RENDER_AVAILABLE = False
    render_malbolge_session = None


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="malbolge-translate",
        description="Translate text to pure Malbolge programs",
    )
    parser.add_argument("input", nargs="?", help="Input text or file path")
    parser.add_argument("--direct", action="store_true", help="Treat input as direct text")
    parser.add_argument("--file", type=Path, help="Input file path")
    
    parser.add_argument("--max-depth", type=int, default=5, help="Max search depth (default: 5)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    parser.add_argument("--no-lexicon", action="store_true", help="Disable Unicode transliteration")
    
    parser.add_argument("--output-dir", type=Path, default="malbolge_output", help="Output directory")
    parser.add_argument("--base-name", default="output", help="Base filename")
    
    parser.add_argument("--execute", action="store_true", help="Execute after generation")
    parser.add_argument("--max-steps", type=int, default=5_000_000, help="Max execution steps")
    
    parser.add_argument("--quijote", action="store_true", help="Generate Don Quijote (downloads if needed)")
    
    parser.add_argument("--lexicon-add", nargs=2, metavar=("CHAR", "REPL"), action="append", help="Add custom lexicon mapping")
    parser.add_argument("--lexicon-file", type=Path, help="Load custom lexicon from JSON file")
    
    args = parser.parse_args(argv)
    
    # Initialize translator
    lexicon = None if args.no_lexicon else Lexicon()
    if args.lexicon_file:
        if lexicon:
            lexicon.import_custom(args.lexicon_file)
    if args.lexicon_add:
        if lexicon:
            for char, repl in args.lexicon_add:
                lexicon.add(char, repl)
    
    translator = MalbolgeTranslator(
        max_search_depth=args.max_depth,
        random_seed=args.seed,
        lexicon=lexicon,
    )
    
    
    
    # Handle Quijote generation
    if args.quijote:
        return generate_quijote(translator, args)
    
    # Get input text
    if args.file:
        text = load_text(args.file)
    elif args.direct or args.input:
        text = args.input or ""
    else:
        # Read from stdin
        text = sys.stdin.read()
    
    if not text:
        parser.error("No input text provided")
    
    print(f"[INFO] Input: {len(text)} chars")
    
    # Translate
    def progress(i, total, word):
        if i % 10 == 0:
            print(f"  Progress: {i+1}/{total} words")
    
    result = translator.translate(text, progress_callback=progress)
    
    # Save
    result.save_all(args.output_dir, args.base_name)
    translator.save_cache()
    
    print(f"\n[SUMMARY]")
    print(f"  Words: {len(result.words)}")
    print(f"  Opcodes: {len(result.full_opcodes)}")
    print(f"  Program: {len(result.full_program)} chars")
    print(f"  Evaluations: {result.stats['evaluations']}")
    print(f"  Time: {result.stats['duration_s']:.2f}s")
    print(f"  Anchors: {result.stats['anchors_used']}")
    
    # Execute
    if args.execute:
        print()
        translator.execute(result, max_steps=args.max_steps)
    
    return 0


def generate_quijote(translator: MalbolgeTranslator, args) -> int:
    """Generate full Don Quijote in Malbolge."""
    import urllib.request
    
    print("[QUIJOTE] Generating Don Quijote in Malbolge...")
    
    # Try to load from file, otherwise download
    quijote_path = Path("quijote.txt")
    if not quijote_path.exists():
        print("[QUIJOTE] Downloading Don Quijote from Project Gutenberg...")
        url = "https://www.gutenberg.org/cache/epub/996/pg996.txt"
        try:
            urllib.request.urlretrieve(url, quijote_path)
            print("[QUIJOTE] Downloaded")
        except Exception as e:
            print(f"[QUIJOTE] Download failed: {e}")
            print("[QUIJOTE] Using first chapter only as demo")
            text = """En un lugar de la Mancha, de cuyo nombre no quiero acordarme, no ha mucho tiempo que vivia un hidalgo de los de lanza en astillero, adarga antigua, rocin flaco y galgo corredor."""
        else:
            text = quijote_path.read_text(encoding="utf-8")
            # Extract just the novel content (skip Gutenberg header/footer)
            start = text.find("*** START OF THE PROJECT GUTENBERG EBOOK")
            end = text.find("*** END OF THE PROJECT GUTENBERG EBOOK")
            if start != -1 and end != -1:
                text = text[start:end]
                text = text[text.find("\n\n")+2:]
    else:
        text = quijote_path.read_text(encoding="utf-8")
    
    print(f"[QUIJOTE] Text length: {len(text):,} chars")
    print(f"[QUIJOTE] Estimated words: ~{len(text.split()):,}")
    
    def progress(i, total, word):
        if i % 100 == 0:
            pct = (i / total) * 100
            print(f"  Progress: {i}/{total} words ({pct:.1f}%)")
    
    result = translator.translate(text, progress_callback=progress)
    
    # Save
    output_dir = args.output_dir or Path("quijote_malbolge")
    result.save_all(output_dir, "quijote")
    
    print(f"\n[QUIJOTE COMPLETE]")
    print(f"  Words: {len(result.words):,}")
    print(f"  Opcodes: {len(result.full_opcodes):,}")
    print(f"  Program: {len(result.full_program):,} chars ({len(result.full_program)/1e6:.1f} MB)")
    print(f"  Time: {result.stats['duration_s']:.1f}s")
    
    # Execute verification
    if args.execute:
        print("[QUIJOTE] Verifying execution...")
        translator.execute(result, max_steps=args.max_steps)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())