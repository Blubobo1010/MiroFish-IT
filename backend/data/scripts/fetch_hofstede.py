"""
Fetch Hofstede 6D cultural dimensions for Italy.
Source: Hofstede Insights (published values, public domain).
Granularity: National (IT).

The 6 dimensions:
- PDI: Power Distance Index
- IDV: Individualism vs Collectivism
- MAS: Masculinity vs Femininity
- UAI: Uncertainty Avoidance Index
- LTO: Long Term Orientation
- IVR: Indulgence vs Restraint
"""

import json
import os

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'raw', 'hofstede')

# Published Hofstede scores for Italy (source: hofstede-insights.com)
# These are well-established, widely cited values used in cross-cultural research.
ITALY_HOFSTEDE = {
    "country": "Italy",
    "country_code": "IT",
    "source": "Hofstede Insights — 6-D Model of National Culture",
    "url": "https://www.hofstede-insights.com/country/italy/",
    "dimensions": {
        "PDI": {
            "score": 50,
            "label": "Power Distance",
            "description": "Italy scores 50 — a medium level. In Northern Italy hierarchy is less felt and there is more equality, while Southern Italy tends to be more hierarchical."
        },
        "IDV": {
            "score": 76,
            "label": "Individualism",
            "description": "Italy is an individualist culture (76). Individual achievement is valued, especially in Northern regions. Southern Italy shows more collectivist traits with stronger family ties."
        },
        "MAS": {
            "score": 70,
            "label": "Masculinity",
            "description": "Italy scores 70 — a masculine society. Competition, success and achievement are important drivers. Children are taught that winning is important."
        },
        "UAI": {
            "score": 75,
            "label": "Uncertainty Avoidance",
            "description": "Italy scores 75 — high uncertainty avoidance. Italians prefer clear structures, rules and planning. Bureaucracy and formality serve to reduce ambiguity."
        },
        "LTO": {
            "score": 61,
            "label": "Long Term Orientation",
            "description": "Italy scores 61 — a pragmatic culture. Italians believe truth depends on situation, context and time. They show ability to adapt traditions to changed conditions."
        },
        "IVR": {
            "score": 30,
            "label": "Indulgence",
            "description": "Italy scores 30 — a restrained culture. Societies with low IVR tend to cynicism and pessimism, control gratification of desires, and feel that social norms restrain their actions."
        }
    },
    # Flat scores for easy integration
    "scores": {
        "PDI": 50,
        "IDV": 76,
        "MAS": 70,
        "UAI": 75,
        "LTO": 61,
        "IVR": 30
    },
    # Qualitative regional variation notes (not official Hofstede data,
    # but well-documented in literature for intra-national differentiation)
    "regional_notes": {
        "north": {
            "description": "Northern Italy (Lombardia, Piemonte, Veneto, Emilia-Romagna, etc.)",
            "tendencies": {
                "PDI": "Lower — flatter hierarchies, more egalitarian workplaces",
                "IDV": "Higher — stronger individual achievement orientation",
                "MAS": "Similar or slightly higher — competitive business culture",
                "UAI": "Similar — structured but pragmatic",
                "LTO": "Higher — stronger long-term investment orientation",
                "IVR": "Similar — restrained but with higher work-life balance focus"
            }
        },
        "center": {
            "description": "Central Italy (Toscana, Lazio, Umbria, Marche)",
            "tendencies": {
                "PDI": "Medium — balanced between north and south",
                "IDV": "Medium-high — mix of individual and community orientation",
                "MAS": "Medium — quality of life emphasis (especially Toscana)",
                "UAI": "Medium-high — bureaucratic center (Roma)",
                "LTO": "Medium — pragmatic but tradition-aware",
                "IVR": "Medium — cultural richness as outlet"
            }
        },
        "south": {
            "description": "Southern Italy (Campania, Puglia, Calabria, Sicilia, Sardegna, etc.)",
            "tendencies": {
                "PDI": "Higher — more hierarchical social structures",
                "IDV": "Lower — stronger family and community bonds",
                "MAS": "Medium — family achievement over individual",
                "UAI": "Higher — stronger need for certainty and stability",
                "LTO": "Lower — more tradition-oriented",
                "IVR": "Lower — more restrained, stronger social norms"
            }
        }
    }
}

# Reference comparison countries (for paper context)
REFERENCE_COUNTRIES = {
    "US": {"PDI": 40, "IDV": 91, "MAS": 62, "UAI": 46, "LTO": 26, "IVR": 68},
    "UK": {"PDI": 35, "IDV": 89, "MAS": 66, "UAI": 35, "LTO": 51, "IVR": 69},
    "DE": {"PDI": 35, "IDV": 67, "MAS": 66, "UAI": 65, "LTO": 83, "IVR": 40},
    "FR": {"PDI": 68, "IDV": 71, "MAS": 43, "UAI": 86, "LTO": 63, "IVR": 48},
    "ES": {"PDI": 57, "IDV": 51, "MAS": 42, "UAI": 86, "LTO": 48, "IVR": 44},
    "CN": {"PDI": 80, "IDV": 20, "MAS": 66, "UAI": 30, "LTO": 87, "IVR": 24},
    "JP": {"PDI": 54, "IDV": 46, "MAS": 95, "UAI": 92, "LTO": 88, "IVR": 42},
}


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Save Italy data
    output_path = os.path.join(OUTPUT_DIR, 'italy_hofstede_6d.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(ITALY_HOFSTEDE, f, ensure_ascii=False, indent=2)
    print(f"[Hofstede] Italy 6D scores saved to {output_path}")

    # Save reference countries
    ref_path = os.path.join(OUTPUT_DIR, 'reference_countries.json')
    with open(ref_path, 'w', encoding='utf-8') as f:
        json.dump(REFERENCE_COUNTRIES, f, ensure_ascii=False, indent=2)
    print(f"[Hofstede] Reference countries saved to {ref_path}")

    # Print summary
    print("\n[Hofstede] Italy 6D Cultural Dimensions:")
    for dim, score in ITALY_HOFSTEDE["scores"].items():
        label = ITALY_HOFSTEDE["dimensions"][dim]["label"]
        print(f"  {dim} ({label}): {score}/100")


if __name__ == '__main__':
    main()
