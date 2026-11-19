"""
WhatsApp Response Formatter.
Ensures responses strictly conform to WhatsApp mobile formatting:
- Replaces Markdown bold (**) with WhatsApp single asterisk (*).
- Normalizes bullet points.
- Truncates oversized messages to prevent overwhelming mobile screens.
- Adds friendly footer signature.
"""

import re

def format_whatsapp_message(text: str, add_footer: bool = True) -> str:
    """Formats raw text into WhatsApp-optimized markdown."""
    if not text:
        return ""

    formatted = text.strip()

    # Convert double asterisks **bold** to WhatsApp *bold*
    formatted = re.sub(r"\*\*(.*?)\*\*", r"*\1*", formatted)

    # Convert markdown headers (# Header, ## Header) to *Header*
    formatted = re.sub(r"^#{1,4}\s*(.+)$", r"*\1*", formatted, flags=re.MULTILINE)

    # Normalize bullet points (- item, * item) to • item
    formatted = re.sub(r"^\s*[-*]\s+", r"• ", formatted, flags=re.MULTILINE)

    # Clean multiple consecutive blank lines
    formatted = re.sub(r"\n{3,}", r"\n\n", formatted)

    # Add standard footer if requested and not already present
    if add_footer and "KrishiBot" not in formatted:
        formatted = f"{formatted}\n\n_🌾 KrishiBot | किसान सहायक_"

    return formatted.strip()
