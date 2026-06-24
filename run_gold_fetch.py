import sys
sys.path.insert(0, '/app')
from database.connection import get_session
from pipelines.gold_reserves import run_gold_reserves_fetch
db = get_session()
r = run_gold_reserves_fetch(db)
print(r)
db.close()
