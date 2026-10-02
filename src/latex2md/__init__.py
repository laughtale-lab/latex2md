"""Structured LaTeX-to-mdBook conversion with Diabat semantic adapters."""
__version__ = '0.1.3'
from .converter import convert, Converter, ConversionError
__all__ = ['convert', 'Converter', 'ConversionError']
