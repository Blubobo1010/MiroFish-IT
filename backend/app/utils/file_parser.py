"""
Strumenti di analisi file
Supporta l'estrazione di testo da file PDF, Markdown e TXT
"""

import os
from pathlib import Path
from typing import List, Optional


def _read_text_with_fallback(file_path: str) -> str:
    """
    Legge un file di testo, in caso di fallimento UTF-8 rileva automaticamente la codifica.

    Adotta una strategia di fallback a più livelli:
    1. Prima tenta la decodifica UTF-8
    2. Usa charset_normalizer per rilevare la codifica
    3. Fallback a chardet per rilevare la codifica
    4. Infine usa UTF-8 + errors='replace' come ultima risorsa

    Args:
        file_path: Percorso del file

    Returns:
        Contenuto testuale decodificato
    """
    data = Path(file_path).read_bytes()

    # Prima tenta UTF-8
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        pass

    # Tenta di usare charset_normalizer per rilevare la codifica
    encoding = None
    try:
        from charset_normalizer import from_bytes
        best = from_bytes(data).best()
        if best and best.encoding:
            encoding = best.encoding
    except Exception:
        pass

    # Fallback a chardet
    if not encoding:
        try:
            import chardet
            result = chardet.detect(data)
            encoding = result.get('encoding') if result else None
        except Exception:
            pass

    # Ultima risorsa: usa UTF-8 + replace
    if not encoding:
        encoding = 'utf-8'

    return data.decode(encoding, errors='replace')


class FileParser:
    """Analizzatore di file"""

    SUPPORTED_EXTENSIONS = {'.pdf', '.md', '.markdown', '.txt'}

    @classmethod
    def extract_text(cls, file_path: str) -> str:
        """
        Estrai testo da un file

        Args:
            file_path: Percorso del file

        Returns:
            Contenuto testuale estratto
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File non trovato: {file_path}")

        suffix = path.suffix.lower()

        if suffix not in cls.SUPPORTED_EXTENSIONS:
            raise ValueError(f"Formato file non supportato: {suffix}")

        if suffix == '.pdf':
            return cls._extract_from_pdf(file_path)
        elif suffix in {'.md', '.markdown'}:
            return cls._extract_from_md(file_path)
        elif suffix == '.txt':
            return cls._extract_from_txt(file_path)

        raise ValueError(f"Formato file non elaborabile: {suffix}")

    @staticmethod
    def _extract_from_pdf(file_path: str) -> str:
        """Estrai testo da PDF"""
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise ImportError("È necessario installare PyMuPDF: pip install PyMuPDF")

        text_parts = []
        with fitz.open(file_path) as doc:
            for page in doc:
                text = page.get_text()
                if text.strip():
                    text_parts.append(text)

        return "\n\n".join(text_parts)

    @staticmethod
    def _extract_from_md(file_path: str) -> str:
        """Estrai testo da Markdown, con rilevamento automatico della codifica"""
        return _read_text_with_fallback(file_path)

    @staticmethod
    def _extract_from_txt(file_path: str) -> str:
        """Estrai testo da TXT, con rilevamento automatico della codifica"""
        return _read_text_with_fallback(file_path)

    @classmethod
    def extract_from_multiple(cls, file_paths: List[str]) -> str:
        """
        Estrai testo da più file e uniscili

        Args:
            file_paths: Lista dei percorsi file

        Returns:
            Testo unificato
        """
        all_texts = []

        for i, file_path in enumerate(file_paths, 1):
            try:
                text = cls.extract_text(file_path)
                filename = Path(file_path).name
                all_texts.append(f"=== Documento {i}: {filename} ===\n{text}")
            except Exception as e:
                all_texts.append(f"=== Documento {i}: {file_path} (estrazione fallita: {str(e)}) ===")

        return "\n\n".join(all_texts)


def split_text_into_chunks(
    text: str,
    chunk_size: int = 500,
    overlap: int = 50
) -> List[str]:
    """
    Suddividi il testo in blocchi più piccoli

    Args:
        text: Testo originale
        chunk_size: Numero di caratteri per blocco
        overlap: Numero di caratteri di sovrapposizione

    Returns:
        Lista di blocchi di testo
    """
    if len(text) <= chunk_size:
        return [text] if text.strip() else []

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        # Tenta di suddividere ai confini delle frasi
        if end < len(text):
            # Cerca il separatore di fine frase più vicino
            for sep in ['。', '！', '？', '.\n', '!\n', '?\n', '\n\n', '. ', '! ', '? ']:
                last_sep = text[start:end].rfind(sep)
                if last_sep != -1 and last_sep > chunk_size * 0.3:
                    end = start + last_sep + len(sep)
                    break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        # Il blocco successivo inizia dalla posizione di sovrapposizione
        start = end - overlap if end < len(text) else len(text)

    return chunks
