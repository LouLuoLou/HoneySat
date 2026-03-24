from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure

MONGO_USER = "honeysat_root_1"
MONGO_PASS = "honeysat_rootpass_1234"
MONGO_HOST = "localhost"
MONGO_PORT = 27017
MONGO_DB   = "honeysat_log"

uri = f"mongodb://{MONGO_USER}:{MONGO_PASS}@{MONGO_HOST}:{MONGO_PORT}/{MONGO_DB}?authSource=admin"

try:
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    
    client.admin.command('ping')
    
    print("Successfully connected to MongoDB!")
    
    db = client[MONGO_DB]
    collections = db.list_collection_names()
    for coll_name in collections:
    	print(f"--- Collection: {coll_name} ---")
    	collection = db[coll_name]
        
    	for doc in collection.find():
    		print(doc)
    	print()  
		

except ConnectionFailure:
    print("❌ Could not connect to MongoDB. Is the container running and port exposed?")
except OperationFailure as e:
    print(f"❌ Authentication failed: {e}")
