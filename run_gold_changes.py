import sys
sys.path.insert(0, "/app")
from database.connection import get_session
from pipelines.gold_reserve_changes import run_gold_reserve_changes_fetch
db = get_session()
r = run_gold_reserve_changes_fetch(db)
print(r)
db.close()
