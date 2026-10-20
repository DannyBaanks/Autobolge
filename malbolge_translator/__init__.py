"""
Malbolge Translator - Generate pure Malbolge programs for arbitrary text.

A standalone tool for translating any text (including Unicode) into
executable Malbolge programs using anchor harness technology.
"""

try:
    from .translator import MalbolgeTranslator, TranslationResult, WordResult
except ImportError:
    MalbolgeTranslator = TranslationResult = WordResult = None

try:
    from .lexicon import Lexicon, transliterate, DEFAULT_LEXICON
except ImportError:
    Lexicon = transliterate = DEFAULT_LEXICON = None

try:
    from .anchor import AnchorManager, AnchorState, WordBank, BankEntry
except ImportError:
    AnchorManager = AnchorState = WordBank = BankEntry = None

from .streaming import translate_continuous, StreamingResult, StreamingSegment

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
    "translate_continuous",
    "StreamingResult",
    "StreamingSegment",
]
