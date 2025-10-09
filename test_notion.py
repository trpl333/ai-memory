import os
from notion_client import Client

token = os.getenv("NOTION_TOKEN")
database_id = os.getenv("NOTION_DATABASE_ID")

if not token or not database_id:
    print("❌ Missing NOTION_TOKEN or NOTION_DATABASE_ID in environment.")
    exit()

notion = Client(auth=token)

try:
    db = notion.databases.retrieve(database_id)
    print("✅ SUCCESS: Connected to Notion!")
    print("Database title:", db["title"][0]["plain_text"])
except Exception as e:
    print("❌ ERROR connecting to Notion:")
    print(e)

