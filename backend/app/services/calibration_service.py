"""
Servizio di Calibrazione Istituzionale (ICF).
Carica i profili di calibrazione NUTS-2 e fornisce contesto regionale
per l'iniezione nelle persona degli agenti.
"""

import json
import os
import random
from typing import Dict, Any, Optional, List

from ..utils.logger import get_logger

logger = get_logger('mirofish.calibration')

# Path ai dati di calibrazione
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'processed')

# NUTS-2 regions raggruppate per zona culturale
CULTURAL_ZONES = {
    "north": ["ITC1", "ITC2", "ITC3", "ITC4", "ITH1", "ITH2", "ITH3", "ITH4", "ITH5"],
    "center": ["ITI1", "ITI2", "ITI3", "ITI4"],
    "south": ["ITF1", "ITF2", "ITF3", "ITF4", "ITF5", "ITF6", "ITG1", "ITG2"],
}

ALL_NUTS2_CODES = [code for codes in CULTURAL_ZONES.values() for code in codes]


class CalibrationService:
    """Fornisce dati di calibrazione regionale per la generazione profili agenti."""

    _instance = None
    _profiles: Dict[str, Any] = {}
    _texts: Dict[str, str] = {}
    _loaded: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._loaded:
            self._load_data()

    def _load_data(self):
        """Carica i file di calibrazione dal disco."""
        profiles_path = os.path.join(DATA_DIR, 'calibration_profiles.json')
        texts_path = os.path.join(DATA_DIR, 'calibration_texts.json')

        if os.path.exists(profiles_path):
            with open(profiles_path, 'r', encoding='utf-8') as f:
                self._profiles = json.load(f)
            logger.info(f"Caricati {len(self._profiles)} profili di calibrazione")
        else:
            logger.warning(f"File calibrazione non trovato: {profiles_path}")

        if os.path.exists(texts_path):
            with open(texts_path, 'r', encoding='utf-8') as f:
                self._texts = json.load(f)
            logger.info(f"Caricati {len(self._texts)} testi di calibrazione")
        else:
            logger.warning(f"File testi calibrazione non trovato: {texts_path}")

        self._loaded = True

    def get_profile(self, nuts2_code: str) -> Optional[Dict[str, Any]]:
        """Restituisce il profilo di calibrazione completo per una regione."""
        return self._profiles.get(nuts2_code)

    def get_calibration_text(self, nuts2_code: str) -> Optional[str]:
        """Restituisce il testo di calibrazione per iniezione nel prompt."""
        return self._texts.get(nuts2_code)

    def get_region_name(self, nuts2_code: str) -> str:
        """Restituisce il nome della regione."""
        profile = self._profiles.get(nuts2_code, {})
        return profile.get("name", nuts2_code)

    def get_cultural_zone(self, nuts2_code: str) -> str:
        """Restituisce la zona culturale (north/center/south)."""
        for zone, codes in CULTURAL_ZONES.items():
            if nuts2_code in codes:
                return zone
        return "center"

    def get_random_region(self, zone: Optional[str] = None) -> str:
        """Restituisce un codice NUTS-2 casuale, opzionalmente filtrato per zona."""
        if zone and zone in CULTURAL_ZONES:
            return random.choice(CULTURAL_ZONES[zone])
        return random.choice(ALL_NUTS2_CODES)

    def get_hofstede_scores(self, nuts2_code: str) -> Dict[str, int]:
        """Restituisce i punteggi Hofstede regionali stimati."""
        profile = self._profiles.get(nuts2_code, {})
        hofstede = profile.get("layers", {}).get("cultural", {}).get("hofstede_6d", {})
        return {dim: data.get("regional_estimate", 0) for dim, data in hofstede.items()}

    def get_demographic_data(self, nuts2_code: str) -> Dict[str, Any]:
        """Restituisce i dati demografici regionali."""
        profile = self._profiles.get(nuts2_code, {})
        return profile.get("layers", {}).get("demographic", {})

    def get_economic_data(self, nuts2_code: str) -> Dict[str, Any]:
        """Restituisce i dati economici regionali."""
        profile = self._profiles.get(nuts2_code, {})
        return profile.get("layers", {}).get("economic", {})

    def build_agent_calibration_context(self, nuts2_code: str) -> str:
        """
        Costruisce il contesto di calibrazione completo per un agente.
        Questo testo viene iniettato nel prompt LLM per generare persona calibrate.
        """
        cal_text = self.get_calibration_text(nuts2_code)
        if not cal_text:
            return ""

        profile = self._profiles.get(nuts2_code, {})
        zone = profile.get("cultural_zone", "")
        name = profile.get("name", nuts2_code)

        # Aggiungi interpretazione comportamentale basata su Hofstede
        hofstede = self.get_hofstede_scores(nuts2_code)
        behavioral_hints = self._hofstede_behavioral_hints(hofstede, zone)

        context = f"""
--- CALIBRAZIONE ISTITUZIONALE ({name}, {nuts2_code}) ---
{cal_text}

--- INDICAZIONI COMPORTAMENTALI ---
{behavioral_hints}
--- FINE CALIBRAZIONE ---
"""
        return context.strip()

    def _hofstede_behavioral_hints(self, scores: Dict[str, int], zone: str) -> str:
        """Genera indicazioni comportamentali basate sui punteggi Hofstede."""
        hints = []

        pdi = scores.get("PDI", 50)
        if pdi > 55:
            hints.append("Tende a rispettare la gerarchia e l'autorità, deferente verso figure di potere.")
        elif pdi < 45:
            hints.append("Atteggiamento più egualitario, mette in discussione l'autorità quando necessario.")

        idv = scores.get("IDV", 76)
        if idv > 78:
            hints.append("Forte orientamento individualista, valorizza l'autonomia personale e il merito.")
        elif idv < 70:
            hints.append("Forte senso di appartenenza al gruppo familiare e comunitario, lealtà verso il proprio cerchio sociale.")

        uai = scores.get("UAI", 75)
        if uai > 78:
            hints.append("Elevata avversione all'incertezza: preferisce regole chiare, diffida delle novità, cerca sicurezza.")
        elif uai < 73:
            hints.append("Maggiore tolleranza per l'ambiguità, più aperto a situazioni nuove e non strutturate.")

        mas = scores.get("MAS", 70)
        if mas > 70:
            hints.append("Orientamento competitivo e orientato al successo materiale.")
        elif mas < 68:
            hints.append("Maggiore attenzione alla qualità della vita e alle relazioni interpersonali.")

        lto = scores.get("LTO", 61)
        if lto > 63:
            hints.append("Orientamento al lungo termine: risparmiatore, pragmatico, investe nel futuro.")
        elif lto < 58:
            hints.append("Orientamento più al presente: valorizza le tradizioni e la gratificazione immediata.")

        ivr = scores.get("IVR", 30)
        if ivr < 32:
            hints.append("Moderata restrizione: senso del dovere forte, gratificazione personale subordinata alle norme sociali.")
        elif ivr > 32:
            hints.append("Maggiore indulgenza verso il piacere e il tempo libero.")

        if zone == "south":
            hints.append("Forte legame con la famiglia allargata e la comunità locale. Comunicazione espressiva e calorosa.")
        elif zone == "north":
            hints.append("Stile comunicativo più riservato e diretto. Forte etica del lavoro e senso pratico.")
        elif zone == "center":
            hints.append("Equilibrio tra tradizione e modernità. Apprezzamento per la cultura e il patrimonio storico.")

        return "\n".join(f"- {h}" for h in hints)

    @property
    def available_regions(self) -> List[str]:
        """Lista dei codici NUTS-2 disponibili."""
        return list(self._profiles.keys())

    @property
    def is_loaded(self) -> bool:
        """Indica se i dati di calibrazione sono stati caricati."""
        return self._loaded and len(self._profiles) > 0
