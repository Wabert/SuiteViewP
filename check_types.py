from suiteview.data.repositories import ConnectionRepository

repo = ConnectionRepository()
conns = repo.get_all_connections()

print("\nConnection Types in Database:")
print("=" * 70)
for c in conns:
    print(f"{c.get('connection_id'):3}: {c.get('connection_name'):30} Type: {c.get('connection_type')}")
