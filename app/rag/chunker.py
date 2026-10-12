import re

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])")


def _split_long(paragraph: str, size: int) -> list[str]:
    if len(paragraph) <= size:
        return [paragraph]
    pieces, current = [], ""
    for sentence in _SENTENCE_END.split(paragraph):
        while len(sentence) > size:
            if current:
                pieces.append(current)
                current = ""
            pieces.append(sentence[:size])
            sentence = sentence[size:]
        if len(current) + len(sentence) + 1 > size and current:
            pieces.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current)
    return pieces


def chunk_text(text: str, size: int = 1200, overlap: int = 200) -> list[str]:
    """Paragraph-aware chunking. The most recent heading is carried into each chunk so a chunk retrieved in
    isolation still says which section it belongs to."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current = ""
    heading = ""
    for para in paragraphs:
        if para.startswith("#") and len(para) < 200:
            heading = para
        for piece in _split_long(para, size):
            if current and len(current) + len(piece) + 2 > size:
                chunks.append(current)
                tail = current[-overlap:] if overlap else ""
                if tail and " " in tail:
                    tail = tail[tail.index(" ") + 1:]
                prefix = f"{heading}\n" if heading and not piece.startswith("#") and heading not in tail else ""
                current = f"{prefix}{tail}\n\n{piece}".strip() if tail else f"{prefix}{piece}"
            else:
                current = f"{current}\n\n{piece}".strip()
    if current:
        chunks.append(current)
    return chunks
