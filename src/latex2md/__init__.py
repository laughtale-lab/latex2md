"""Structured LaTeX-to-mdBook conversion with Diabat semantic adapters."""
__version__ = '0.2.0'
from .converter import convert, Converter, ConversionError
__all__ = ['convert', 'Converter', 'ConversionError']
