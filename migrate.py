import pandas as pd
from supabase import Client, create_client

# 1. Supabase Credentials (replace with your actual project details)
SUPABASE_URL = "https://gftvqztvzezjfuzhldie.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImdmdHZxenR2emV6amZ1emhsZGllIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODUzMzQ4NDcsImV4cCI6MjEwMDkxMDg0N30.aoEhmE23Jv61wpoH5V1bREAh5fm9I_lYizkQ2OCuOZs"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 2. Read raw Excel file without forcing a header row index
df_raw = pd.read_excel("Gym_Registre_PG.xlsx", header=None)

# Dynamically find the row index where "Data" appears in any column
header_idx = None
for idx, row in df_raw.iterrows():
  if row.astype(str).str.contains("Data").any():
    header_idx = idx
    break

if header_idx is None:
  raise ValueError(
      "Could not find a row containing 'Data'. Please check the Excel file."
  )

# Reload data starting from the correct header row
df = pd.read_excel("Gym_Registre_PG.xlsx", header=header_idx)
df.columns = df.columns.astype(str).str.strip()

print("Successfully loaded columns:", df.columns.tolist())

# 3. Clean and normalize data
# Drop empty rows where key information is missing
data_col = [c for c in df.columns if "data" in c.lower()][0]
ex_col = [c for c in df.columns if "exercici" in c.lower()][0]

df = df.dropna(subset=[data_col, ex_col], how="any")

# Format date column (YYYY-MM-DD)
df["data_clean"] = pd.to_datetime(df[data_col]).dt.strftime("%Y-%m-%d")

# Safe helper to grab values even if column names vary slightly
def get_col_val(row, keywords, default_val):
  for col in df.columns:
    if any(k.lower() in col.lower() for k in keywords):
      val = row[col]
      return default_val if pd.isna(val) else val
  return default_val


# 4. Prepare payload matching Supabase table columns
records = []
for _, row in df.iterrows():
  records.append({
      "data": str(row["data_clean"]),
      "exercici": str(get_col_val(row, ["exercici"], "")),
      "grup_muscular": str(get_col_val(row, ["grup", "muscular"], "")),
      "pes_kg": float(
          get_col_val(row, ["pes", "volum", "weight"], 0)
      ),  # maps Pes or Volum
      "repeticions": int(get_col_val(row, ["repeticions", "reps"], 0)),
      "temps_min": float(get_col_val(row, ["temps", "min"], 0)),
      "observacions": str(
          get_col_val(row, ["observacions", "notes", "esforç"], "")
      ),
  })

# 5. Push to Supabase
print(f"Uploading {len(records)} rows to Supabase...")
supabase.table("gym_logs").insert(records).execute()
print("Migration successful! Check your Supabase Table Editor.")