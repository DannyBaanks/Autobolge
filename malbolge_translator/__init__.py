"""
Malbolge Translator - Generate pure Malbolge programs for arbitrary text.

A standalone tool for translating any text (including Unicode) into
executable Malbolge programs using anchor harness technology.
"""

from .translator import MalbolgeTranslator, TranslationResult, WordResult
from .lexicon import Lexicon, transliterate, DEFAULT_LEXICON
from .anchor import AnchorManager, AnchorState, WordBank, BankEntry

__version__ = "1.0.0"
__all__ = [
    "MalbolgeTranslator",
    "TranslationResult", 
    "WordResult",
    "Lexicon",
    "transliterate",
    "DEFAULT_LEXICON",
    "AnchorManager",
    "AnchorState",
    "WordBank",
    "BankEntry",
]