"""Rebuild the Sentinel D-0116 (FB batch 2b-1) fixtures. All values invented.

    python tests/fixtures/foreign_bonds/make_fb2b1_fixtures.py

Deterministic: fixed zip timestamps, so a rebuild is byte-identical.
"""
import io
import zipfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
STAMP = (2026, 10, 22, 0, 0, 0)


def write(name, data):
    (HERE / name).write_bytes(data)


def zip_one(member, data):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(zipfile.ZipInfo(member, STAMP), data)
    return buf.getvalue()


# ---------------------------------------------------------------- ECB IRS
IRS_HEADER = ("KEY,FREQ,REF_AREA,IR_TYPE,TR_TYPE,MATURITY_CAT,BS_COUNT_SECTOR,CURRENCY_TRANS,"
              "IR_BUS_COV,IR_FV_TYPE,TIME_PERIOD,OBS_VALUE,OBS_STATUS,TITLE")
IRS = {"ES": ("3.50", "3.60"), "GR": ("3.70", "3.80"), "IT": ("3.90", "4.00"),
       "PL": ("5.50", "5.60"), "PT": ("3.40", "")}


def irs_csv():
    lines = [IRS_HEADER]
    for cc, (aug, sep) in IRS.items():
        cur = "PLN" if cc == "PL" else "EUR"
        for month, v in (("2026-08", aug), ("2026-09", sep)):
            lines.append(f"IRS.M.{cc}.L.L40.CI.0000.{cur}.N.Z,M,{cc},L,L40,CI,0000,{cur},N,Z,"
                         f"{month},{v},A,\"Long-term interest rate for convergence purposes, {cc}\"")
    return ("\n".join(lines) + "\n").encode()


# ---------------------------------------------------------------- BdI BMK0100
BMK_COLS = ["DATA_OSS", "MFN_BMK.M.001A.922.0.EUR.9", "MFN_BMK.M.020.922.0.EUR.203",
            "MFN_BMK.M.020.922.0.EUR.205", "MFN_BMK.M.020.922.0.EUR.210",
            "MFN_BMK.M.020.922.0.EUR.230", "MFN_BMK.M.035A.922.0.EUR.9"]
BMK_ROWS = [
    ("2026/09/30", "", "3.1", "3.3", "3.9", "4.6", "3.0"),
    ("2026/08/31", "", "3.0", "3.2", "3.8", "", "2.9"),
    ("2026/07/31", "", "2.9", "3.1", "3.7", "4.4", "2.8"),
]


def bmk_csv(rows=BMK_ROWS, cols=BMK_COLS, decimal="."):
    q = lambda c: f'"{c}"'
    out = [";".join(q(c) for c in cols)]
    for r in rows:
        out.append(";".join(q(c.replace(".", decimal) if i else c) for i, c in enumerate(r)))
    return ("\n".join(out) + "\n").encode()


# ---------------------------------------------------------------- MinFin PL
PL_HEADER = ["#ID", "DataTransakcji", "TypOperacji", "Seria", "DataWykupu", "Kupon", "CenaŚr", "RentŚr"]
PL_ROWS = [
    # auction 2026-10-08
    (1, datetime(2026, 10, 8), "AS", "OK0728", datetime(2028, 7, 25), 0, 90.0, 0.0480),
    (2, datetime(2026, 10, 8), "AS", "PS0431", datetime(2031, 4, 25), 0.05, 99.0, 0.0560),
    (3, datetime(2026, 10, 8), "AS", "DS0436", datetime(2036, 4, 25), 0.05, 95.0, 0.0600),
    # auction 2026-10-22: two 10Y candidates, DS0436 (9.51y) is closer than DS1034 (8.01y)
    (4, datetime(2026, 10, 22), "AS", "OK0129", datetime(2029, 1, 25), 0, 89.0, 0.0500),
    (5, datetime(2026, 10, 22), "AS", "PS1031", datetime(2031, 10, 25), 0.05, 98.0, 0.0580),
    (6, datetime(2026, 10, 22), "AS", "DS1034", datetime(2034, 10, 25), 0.05, 96.0, 0.0700),
    (7, datetime(2026, 10, 22), "AS", "DS0436", datetime(2036, 4, 25), 0.05, 95.0, 0.0620),
    # ignored: floating rate, a switch auction, a blank yield, an out-of-bucket bond
    (8, datetime(2026, 10, 22), "AS", "WZ1131", datetime(2031, 11, 25), "FRN", 99.0, 0.0510),
    (9, datetime(2026, 10, 22), "AZ", "PS1031", datetime(2031, 10, 25), 0.05, 98.0, 0.0999),
    (10, datetime(2026, 10, 22), "AS", "OK0727", datetime(2027, 7, 25), 0, 97.0, None),
    (11, datetime(2026, 10, 22), "AS", "WS0447", datetime(2047, 4, 25), 0.04, 80.0, 0.0650),
]


def pl_xlsm(rows=PL_ROWS, sheet="Operacje", header=PL_HEADER):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(header)
    for r in rows:
        ws.append(list(r))
    wb.create_sheet("Zadłużenie").append(["synthetic"])
    buf = io.BytesIO()
    wb.save(buf)
    # Make it an .xlsm: a (dummy, never-executed) VBA part plus its content type.
    src = zipfile.ZipFile(io.BytesIO(buf.getvalue()))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for info in src.infolist():
            data = src.read(info)
            if info.filename == "[Content_Types].xml":
                data = data.replace(
                    b"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
                    b"application/vnd.ms-excel.sheet.macroEnabled.main+xml",
                ).replace(b"</Types>", b'<Override PartName="/xl/vbaProject.bin" '
                          b'ContentType="application/vnd.ms-office.vbaProject"/></Types>')
            zf.writestr(zipfile.ZipInfo(info.filename, STAMP), data)
        zf.writestr(zipfile.ZipInfo("xl/vbaProject.bin", STAMP), b"SYNTHETIC-NOT-VBA")
    return out.getvalue()


PL_PAGE = b"""<!DOCTYPE html><html><body>
<a href="/attachment/d21697dc-0000-4000-8000-000000000001">Bony skarbowe</a>
<a href="/attachment/2b7486af-0000-4000-8000-000000000002">Obligacje hurtowe</a>
<a href="/attachment/2b7486af-0000-4000-8000-000000000002">again</a>
</body></html>
"""

if __name__ == "__main__":
    write("ecb_irs.csv", irs_csv())
    write("ecb_irs_header_only.csv", (IRS_HEADER + "\n").encode())
    write("bdi_bmk0100.csv", bmk_csv())
    write("bdi_bmk0100.zip", zip_one("20261009_000000-TIMESERIES-MULTICUBE.csv", bmk_csv()))
    write("bdi_bmk0100_it_decimal.csv", bmk_csv(decimal=","))
    write("minfin_obligacje_hurtowe.xlsm", pl_xlsm())
    write("minfin_page.html", PL_PAGE)
