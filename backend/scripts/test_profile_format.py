"""
Test per verificare che la generazione del formato Profile sia conforme ai requisiti OASIS
Verifica:
1. Twitter Profile genera formato CSV
2. Reddit Profile genera formato JSON dettagliato
"""

import os
import sys
import json
import csv
import tempfile

# Aggiungere il percorso del progetto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.oasis_profile_generator import OasisProfileGenerator, OasisAgentProfile


def test_profile_formats():
    """Testare i formati Profile"""
    print("=" * 60)
    print("Test formato Profile OASIS")
    print("=" * 60)

    # Creare dati Profile di test
    test_profiles = [
        OasisAgentProfile(
            user_id=0,
            user_name="test_user_123",
            name="Test User",
            bio="A test user for validation",
            persona="Test User is an enthusiastic participant in social discussions.",
            karma=1500,
            friend_count=100,
            follower_count=200,
            statuses_count=500,
            age=25,
            gender="male",
            mbti="INTJ",
            country="China",
            profession="Student",
            interested_topics=["Technology", "Education"],
            source_entity_uuid="test-uuid-123",
            source_entity_type="Student",
        ),
        OasisAgentProfile(
            user_id=1,
            user_name="org_official_456",
            name="Official Organization",
            bio="Official account for Organization",
            persona="This is an official institutional account that communicates official positions.",
            karma=5000,
            friend_count=50,
            follower_count=10000,
            statuses_count=200,
            profession="Organization",
            interested_topics=["Public Policy", "Announcements"],
            source_entity_uuid="test-uuid-456",
            source_entity_type="University",
        ),
    ]

    generator = OasisProfileGenerator.__new__(OasisProfileGenerator)

    # Usare una directory temporanea
    with tempfile.TemporaryDirectory() as temp_dir:
        twitter_path = os.path.join(temp_dir, "twitter_profiles.csv")
        reddit_path = os.path.join(temp_dir, "reddit_profiles.json")

        # Testare il formato CSV di Twitter
        print("\n1. Test Twitter Profile (formato CSV)")
        print("-" * 40)
        generator._save_twitter_csv(test_profiles, twitter_path)

        # Leggere e verificare il CSV
        with open(twitter_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        print(f"   File: {twitter_path}")
        print(f"   Righe: {len(rows)}")
        print(f"   Intestazione: {list(rows[0].keys())}")
        print(f"\n   Dati di esempio (riga 1):")
        for key, value in rows[0].items():
            print(f"     {key}: {value}")

        # Verificare i campi obbligatori
        required_twitter_fields = ['user_id', 'user_name', 'name', 'bio',
                                   'friend_count', 'follower_count', 'statuses_count', 'created_at']
        missing = set(required_twitter_fields) - set(rows[0].keys())
        if missing:
            print(f"\n   [ERRORE] Campi mancanti: {missing}")
        else:
            print(f"\n   [SUPERATO] Tutti i campi obbligatori sono presenti")

        # Testare il formato JSON di Reddit
        print("\n2. Test Reddit Profile (formato JSON dettagliato)")
        print("-" * 40)
        generator._save_reddit_json(test_profiles, reddit_path)

        # Leggere e verificare il JSON
        with open(reddit_path, 'r', encoding='utf-8') as f:
            reddit_data = json.load(f)

        print(f"   File: {reddit_path}")
        print(f"   Voci: {len(reddit_data)}")
        print(f"   Campi: {list(reddit_data[0].keys())}")
        print(f"\n   Dati di esempio (voce 1):")
        print(json.dumps(reddit_data[0], ensure_ascii=False, indent=4))

        # Verificare i campi del formato dettagliato
        required_reddit_fields = ['realname', 'username', 'bio', 'persona']
        optional_reddit_fields = ['age', 'gender', 'mbti', 'country', 'profession', 'interested_topics']

        missing = set(required_reddit_fields) - set(reddit_data[0].keys())
        if missing:
            print(f"\n   [ERRORE] Campi obbligatori mancanti: {missing}")
        else:
            print(f"\n   [SUPERATO] Tutti i campi obbligatori sono presenti")

        present_optional = set(optional_reddit_fields) & set(reddit_data[0].keys())
        print(f"   [INFO] Campi opzionali: {present_optional}")

    print("\n" + "=" * 60)
    print("Test completato!")
    print("=" * 60)


def show_expected_formats():
    """Mostrare i formati attesi da OASIS"""
    print("\n" + "=" * 60)
    print("Riferimento formati Profile attesi da OASIS")
    print("=" * 60)

    print("\n1. Twitter Profile (formato CSV)")
    print("-" * 40)
    twitter_example = """user_id,user_name,name,bio,friend_count,follower_count,statuses_count,created_at
0,user0,User Zero,I am user zero with interests in technology.,100,150,500,2023-01-01
1,user1,User One,Tech enthusiast and coffee lover.,200,250,1000,2023-01-02"""
    print(twitter_example)

    print("\n2. Reddit Profile (formato JSON dettagliato)")
    print("-" * 40)
    reddit_example = [
        {
            "realname": "James Miller",
            "username": "millerhospitality",
            "bio": "Passionate about hospitality & tourism.",
            "persona": "James is a seasoned professional in the Hospitality & Tourism industry...",
            "age": 40,
            "gender": "male",
            "mbti": "ESTJ",
            "country": "UK",
            "profession": "Hospitality & Tourism",
            "interested_topics": ["Economics", "Business"]
        }
    ]
    print(json.dumps(reddit_example, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    test_profile_formats()
    show_expected_formats()
