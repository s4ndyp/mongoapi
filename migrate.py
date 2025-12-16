import os
from pymongo import MongoClient

# 1. Configuratie (Gebruik dezelfde URI als in app.py)
# Pas dit aan als uw database op een ander adres zit
MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://mongo:27017/') 
DB_NAME = 'data_store'

def migrate_client_data():
    try:
        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]
        print("Verbonden met database.")
    except Exception as e:
        print(f"Kon niet verbinden: {e}")
        return

    # Vraag om input
    collection_name = input("Voer de naam van de collectie in (bijv. 'test_data'): ").strip()
    if collection_name not in db.list_collection_names():
        print(f"Let op: Collectie '{collection_name}' bestaat niet of is leeg.")
        if input("Doorgaan? (j/n): ").lower() != 'j':
            return

    collection = db[collection_name]

    # Tel hoeveel documenten er totaal zijn
    total_docs = collection.count_documents({})
    print(f"Totaal aantal documenten in '{collection_name}': {total_docs}")

    # Vraag om het NIEUWE Client ID (waar de data naartoe moet)
    new_client_id = input("Voer het NIEUWE Client ID in (waarnaartoe gemigreerd moet worden): ").strip()
    
    # Optie A: Alles overzetten wat nog GEEN client_id heeft (oude data)
    # Optie B: Alles overzetten van een specifiek OUD ID
    print("\nKies een migratie strategie:")
    print("1. Zet ALLE documenten in deze collectie over naar het nieuwe ID")
    print("2. Zet alleen documenten over van een specifiek OUD Client ID")
    
    choice = input("Keuze (1 of 2): ").strip()

    filter_query = {}
    
    if choice == '2':
        old_id = input("Voer het OUDE Client ID in: ").strip()
        filter_query = {'client_id': old_id}
    else:
        # Bij keuze 1: Wees voorzichtig dat je niet data van ANDERE actieve clients overschrijft
        # We filteren op alles wat NIET het nieuwe ID is
        filter_query = {'client_id': {'$ne': new_client_id}}

    count_to_migrate = collection.count_documents(filter_query)
    
    if count_to_migrate == 0:
        print("Geen documenten gevonden die voldoen aan de criteria.")
        return

    print(f"\nStaat op het punt om {count_to_migrate} documenten toe te wijzen aan Client ID: {new_client_id}")
    confirm = input("Type 'JA' om te bevestigen: ")

    if confirm == 'JA':
        result = collection.update_many(
            filter_query,
            {'$set': {'client_id': new_client_id}}
        )
        print(f"Succes! {result.modified_count} documenten bijgewerkt.")
    else:
        print("Geannuleerd.")

if __name__ == "__main__":
    migrate_client_data()
