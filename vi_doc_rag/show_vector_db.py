import sys
sys.stdout.reconfigure(encoding="utf-8")

import chromadb

client = chromadb.PersistentClient(path="vi_doc_rag/vector_db")
collection = client.get_collection("tai_lieu_tieng_viet")
data = collection.get(include=["documents", "metadatas", "embeddings"], limit=5)

print("Số chunk trong database:", collection.count())

for i, chunk_id in enumerate(data["ids"]):
    metadata = data["metadatas"][i] or {}
    vector = data["embeddings"][i]

    print("\n" + "=" * 60)
    print("ID:", chunk_id)
    print("Nguồn:", metadata.get("source"))
    print("Trang:", metadata.get("page_start"), "-", metadata.get("page_end"))
    print("Nội dung:", (data["documents"][i] or "")[:250])
    print("Số chiều vector:", len(vector))
    print("5 giá trị vector đầu:", vector[:5].tolist())