# Treasury Monitor

A comprehensive system for tracking US Treasury bonds, oil prices, gold holdings, and other USD strength indicators. Designed to monitor macroeconomic relationships and the long-term trajectory of US dollar value.

## Overview

**Phase 1 (ACTIVE):** FRED data integration - Treasury yields (10Y, 5Y, 2Y) and WTI crude oil prices

**Phase 2 (Pending):** US Treasury TIC holdings by country

**Phase 3 (Pending):** Gold reserves by country

## Architecture

- **Database:** PostgreSQL (local)
- **API:** FastAPI with async support
- **Scheduler:** APScheduler for automated data fetching
- **Data Sources:** FRED (Federal Reserve Economic Data), TIC (Treasury International Capital), IMF/World Gold Council

## Prerequisites

- Python 3.10+
- PostgreSQL 12+ (local)
- Git

## Local Setup

### 1. Clone the repository

```bash
git clone <repo-url>
cd treasury-monitor
```

### 2. Create virtual environment

```bash
python -m venv venv
source venv/bin/activate  # macOS/Linux
# or
venv\Scripts\activate  # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set up PostgreSQL

#### Option A: Docker (Recommended for local development)

```bash
docker run -d \
  --name treasury_monitor_db \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=treasury_monitor \
  -p 5432:5432 \
  postgres:15
```

#### Option B: Local PostgreSQL installation

```bash
# macOS with Homebrew
brew install postgresql
brew services start postgresql

# Linux (Ubuntu/Debian)
sudo apt-get install postgresql postgresql-contrib
sudo systemctl start postgresql

# Then create database
psql -U postgres -c "CREATE DATABASE treasury_monitor;"
```

### 5. Configure environment

```bash
cp .env.template .env
# Edit .env and add your FRED API key (get free at https://fred.stlouisfed.org/docs/api/)
```

### 6. Initialize database and start

```bash
python main.py
```

The API will start on `http://localhost:8000`

Access:
- **API Docs:** http://localhost:8000/docs
- **Health Check:** http://localhost:8000/api/health

## API Endpoints

### System

- `GET /` - Root endpoint
- `GET /api/health` - System health and last update times
- `GET /api/stats` - Database statistics

### Data

- `GET /api/metrics` - List all available metrics
- `GET /api/countries` - List all countries in database
- `GET /api/timeseries?metric_codes=DGS10,DCOILWTICO` - Query multiple metrics
- `GET /api/metric/{code}` - Query single metric (shorthand)
- `GET /api/pipeline-logs` - Pipeline execution history

### Examples

**Get Treasury 10-year yield for last 2 years:**

```bash
curl "http://localhost:8000/api/metric/DGS10?start_date=2022-06-20&end_date=2024-06-20"
```

**Get correlation data (Treasury 10Y + Oil):**

```bash
curl "http://localhost:8000/api/timeseries?metric_codes=DGS10,DCOILWTICO&start_date=2022-01-01"
```

**Get all metrics in 'treasury' category:**

```bash
curl "http://localhost:8000/api/metrics?category=treasury"
```

## Configuration

Edit `.env` to customize:

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/treasury_monitor
FRED_API_KEY=your_api_key_here
API_HOST=0.0.0.0
API_PORT=8000
SCHEDULER_ENABLED=true
FRED_FETCH_HOUR=2          # Daily FRED fetch at 2 AM
TREASURY_FETCH_DAY=15       # Monthly on 15th
GOLD_FETCH_DAY=1            # Monthly on 1st
LOG_LEVEL=INFO
```

## Pipeline Execution

### FRED Fetch (Phase 1 - Active)

Fetches daily:
- `DGS10` - US Treasury 10-Year Yield
- `DGS5` - US Treasury 5-Year Yield
- `DGS2` - US Treasury 2-Year Yield
- `DCOILWTICO` - WTI Crude Oil Spot Price

**Runs:** Daily at configured hour (default 2 AM)

### Treasury Holdings (Phase 2 - Placeholder)

**Status:** Implementation pending

**Source:** US Treasury TIC (Treasury International Capital)

**Data:** Monthly holdings by country

**Task:** Parse TIC CSV release, create Country records, upsert TimeSeries

### Gold Reserves (Phase 3 - Placeholder)

**Status:** Implementation pending

**Source:** IMF/World Gold Council

**Data:** Gold holdings by country (annual/quarterly)

**Task:** Determine best source, parse data, create Country records, upsert TimeSeries

## Database Schema

### Core Tables

**metrics** - Metric definitions (Treasury yields, oil, gold, etc.)

```
id, code, name, category, unit, source, description, created_at
```

**countries** - Country/region reference

```
id, iso_code, name, region, created_at
```

**timeseries** - Time-series data points

```
id, metric_id, country_id, date, value, created_at, updated_at
```

**update_logs** - Pipeline execution logs

```
id, pipeline_name, status, records_inserted, records_updated, error_message, started_at, completed_at
```

## Monitoring

Check pipeline health:

```bash
curl http://localhost:8000/api/health
```

View recent execution logs:

```bash
curl http://localhost:8000/api/pipeline-logs?limit=10
```

Check for errors:

```bash
curl http://localhost:8000/api/pipeline-logs?pipeline_name=FRED&limit=20
```

## Development

### Add a new metric source

1. Create fetch function in `pipelines/<source>_fetcher.py`
2. Define metrics in `run_<source>_fetch()`
3. Add scheduler job in `pipelines/scheduler.py`
4. Test with manual run: `python -c "from pipelines.<source>_fetcher import run_<source>_fetch; from database.connection import get_session; db = get_session(); print(run_<source>_fetch(db))"`

### Manual data fetch

```python
from database.connection import get_session
from pipelines.fred_fetcher import run_fred_fetch

db = get_session()
result = run_fred_fetch(db)
print(result)
db.close()
```

### Query data directly

```python
from database.connection import get_session
from database.models import TimeSeries, Metric

db = get_session()
metric = db.query(Metric).filter_by(code="DGS10").first()
data = db.query(TimeSeries).filter_by(metric_id=metric.id).order_by(TimeSeries.date.desc()).limit(5).all()

for point in data:
    print(f"{point.date}: {point.value}")

db.close()
```

## Troubleshooting

### Database connection error

Verify PostgreSQL is running:

```bash
psql -U postgres -c "SELECT 1"
```

If using Docker:

```bash
docker ps | grep treasury_monitor_db
```

### FRED API error

- Verify FRED API key in `.env`
- Check API rate limits (FRED allows 120 requests/minute)
- Confirm internet connectivity

### Scheduler not running

- Check `SCHEDULER_ENABLED=true` in `.env`
- Review logs in `treasury_monitor.log`
- Verify database connection is working

### No data in database

1. Check update logs: `GET /api/pipeline-logs`
2. Run manual FRED fetch (see Development section)
3. Review error messages in logs

## Next Steps (Roadmap)

**Short term:**
- [ ] Implement Phase 2: Treasury holdings by country
- [ ] Implement Phase 3: Gold reserves by country
- [ ] Build React UI for visualization with time slider

**Medium term:**
- [ ] Add alerting for significant yield/oil correlation changes
- [ ] Implement data backfill for historical completeness
- [ ] Add caching layer for API responses

**Long term:**
- [ ] Deploy to cloud (AWS/GCP) for persistent monitoring
- [ ] Add predictive modeling for USD strength
- [ ] Integrate additional indicators (M1/M2, forex rates, etc.)

## License

Internal use only.

## Support

For issues or questions, contact the Data & Integration team.
