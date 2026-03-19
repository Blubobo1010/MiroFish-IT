"""
Servizio di elaborazione testo
"""

from typing import List, Optional
from ..utils.file_parser import FileParser, split_text_into_chunks


class TextProcessor:
    """Elaboratore di testo"""

    @staticmethod
    def extract_from_files(file_paths: List[str]) -> str:
        """Estrae il testo da più file"""
        return FileParser.extract_from_multiple(file_paths)

    @staticmethod
    def split_text(
        text: str,
        chunk_size: int = 500,
        overlap: int = 50
    ) -> List[str]:
        """
        Suddivide il testo

        Args:
            text: Testo originale
            chunk_size: Dimensione del blocco
            overlap: Dimensione della sovrapposizione

        Returns:
            Lista di blocchi di testo
        """
        return split_text_into_chunks(text, chunk_size, overlap)

    @staticmethod
    def preprocess_text(text: str) -> str:
        """
        Pre-elaborazione del testo
        - Rimuove gli spazi bianchi in eccesso
        - Normalizza le interruzioni di riga

        Args:
            text: Testo originale

        Returns:
            Testo elaborato
        """
        import re

        # Normalizza le interruzioni di riga
        text = text.replace('\r\n', '\n').replace('\r', '\n')

        # Rimuove le righe vuote consecutive (mantiene al massimo due interruzioni di riga)
        text = re.sub(r'\n{3,}', '\n\n', text)

        # Rimuove gli spazi bianchi all'inizio e alla fine delle righe
        lines = [line.strip() for line in text.split('\n')]
        text = '\n'.join(lines)

        return text.strip()

    @staticmethod
    def get_text_stats(text: str) -> dict:
        """Ottiene le statistiche del testo"""
        return {
            "total_chars": len(text),
            "total_lines": text.count('\n') + 1,
            "total_words": len(text.split()),
        }
