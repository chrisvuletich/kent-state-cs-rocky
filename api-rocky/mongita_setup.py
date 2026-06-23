from mongita import MongitaClientDisk

client = MongitaClientDisk("mongitaDB")
db = client["rockydb"]
col = db["apikeys"]

#col.insert_one({"api-key" : "abcdef123456"})

for doc in col.find():
    print(doc)

#col.delete_one({ "api-key" : "abcdef123456" })
