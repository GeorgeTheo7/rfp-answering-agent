"""Builds eval/fail_test.xlsx, the manual smoke-test RFP. Expected results: eval/SMOKE.md.
Run: .\\venv\\Scripts\\python eval\\make_fail_test.py
"""
import os

import openpyxl
from openpyxl.worksheet.datavalidation import DataValidation

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fail_test.xlsx")

wb = openpyxl.Workbook()

# Sheet 1: dropdown column + "Supported (Yes/No)" header placed before ID (triggers ID bug)
ws = wb.active
ws.title = "Security"
ws.append(["Question", "Supported (Yes/No)", "ID", "Category"])
ws.append(["What is the minimum password length required?", None, "SEC-01", "Security"])
ws.append(["What is the CEO's shoe size?", None, "SEC-02", "Product"])
dv = DataValidation(type="list", formula1='"Yes,No,Partial"')
ws.add_data_validation(dv)
dv.add("B2:B3")

# Sheet 2: no ID column
ws2 = wb.create_sheet("General")
ws2.append(["Question"])
ws2.append(["Is the use of removable storage media restricted?"])

wb.save(OUT)
print(f"Wrote {OUT}")
