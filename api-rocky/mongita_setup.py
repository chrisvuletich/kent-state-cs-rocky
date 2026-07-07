from mongita import MongitaClientDisk

client = MongitaClientDisk("mongitaDB")
db = client["rocky_db"]
col = db["api_keys"]

# Store API keys as SHA-256 hashes in the shared api_keys collection.

for doc in col.find():
    print(doc)
