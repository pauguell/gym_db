import io
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    HRFlowable,
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Table,
    TableStyle,
)

# Target exercises for the dedicated 1RM page
TARGET_1RM_EXERCISES = [
    'Press Pit Mancuerna',
    'Pes Mort',
    'Sentadeta amb Barra',
    'Press Espatlles Mancuerna',
]

# ==========================================
# 1. LOAD & CLEAN DATA
# ==========================================
file_path = 'Gym_Registre_PG.xlsx'
df = pd.read_excel(file_path, sheet_name='Registre_Exercicis', header=3)

df['Data'] = pd.to_datetime(df['Data'], errors='coerce')
df['Pes (kg)'] = pd.to_numeric(df['Pes (kg)'], errors='coerce').fillna(0)
df['Repeticions'] = pd.to_numeric(df['Repeticions'], errors='coerce').fillna(0)
df['Temps (min)'] = pd.to_numeric(df['Temps (min)'], errors='coerce').fillna(0)

df = df.dropna(subset=['Exercici', 'Data']).copy()
df['Exercici'] = df['Exercici'].astype(str).str.strip()
df['Grup Muscular'] = df['Grup Muscular'].astype(str).str.strip()

# Calculate Volume & Estimated 1RM (Brzycki formula)
df['Set_Volume'] = df['Pes (kg)'] * df['Repeticions']
df['Estimated_1RM'] = df.apply(
    lambda r: r['Pes (kg)'] * (36 / (37 - r['Repeticions']))
    if (r['Pes (kg)'] > 0 and 0 < r['Repeticions'] < 37)
    else 0,
    axis=1,
)

# ==========================================
# 2. DATA PROCESSING FOR SUMMARY TABLE
# ==========================================
daily_records = []
for (ex, dt), group in df.groupby(['Exercici', 'Data']):
  mg = group['Grup Muscular'].iloc[0]
  total_vol = group['Set_Volume'].sum()
  total_time = group['Temps (min)'].sum()
  total_reps = group['Repeticions'].sum()
  max_1rm = group['Estimated_1RM'].max()
  num_sets = len(group)

  weights = group['Pes (kg)'].tolist()
  reps = group['Repeticions'].tolist()
  times = group['Temps (min)'].tolist()

  daily_records.append({
      'Exercici': ex,
      'Grup Muscular': mg,
      'Data': dt,
      'Daily_Volume_kg': total_vol,
      'Daily_Time_min': total_time,
      'Daily_Reps': total_reps,
      'Max_Estimated_1RM': max_1rm,
      'Num_Sets': num_sets,
      'Weights_List': weights,
      'Reps_List': reps,
      'Times_List': times,
  })

table_daily_df = pd.DataFrame(daily_records)

# Extract best record day per exercise
final_rows = []
for ex, group in table_daily_df.groupby('Exercici'):
  max_vol = group['Daily_Volume_kg'].max()
  max_time = group['Daily_Time_min'].max()
  max_reps = group['Daily_Reps'].max()

  if max_vol == 0 and max_time > 0:
    best_row = group[group['Daily_Time_min'] == max_time].iloc[-1]
    max_rec_str = f"{best_row['Daily_Time_min']:g} min"
    series_desc = [
        f'Serie {idx+1}: {t:g} min'
        for idx, t in enumerate(best_row['Times_List'])
    ]
  elif max_vol == 0 and max_reps > 0:
    best_row = group[group['Daily_Reps'] == max_reps].iloc[-1]
    max_rec_str = f"{best_row['Daily_Reps']:g} reps"
    series_desc = [
        f'Serie {idx+1}: {r:g} reps'
        for idx, r in enumerate(best_row['Reps_List'])
    ]
  else:
    best_row = group[group['Daily_Volume_kg'] == max_vol].iloc[-1]
    max_rec_str = f"{best_row['Daily_Volume_kg']:g} kg"
    series_desc = []
    for idx, (w, r) in enumerate(
        zip(best_row['Weights_List'], best_row['Reps_List'])
    ):
      if w > 0:
        series_desc.append(f'Serie {idx+1}: {w:g}kg, {r:g} reps')
      else:
        series_desc.append(f'Serie {idx+1}: {r:g} reps')

  final_rows.append({
      'Exercici': ex,
      'Grup Muscular': best_row['Grup Muscular'],
      'Data': best_row['Data'].strftime('%Y-%m-%d'),
      'Max Record': max_rec_str,
      'Detall': '<br/>'.join(series_desc),
  })

res_table = (
    pd.DataFrame(final_rows)
    .sort_values(by=['Grup Muscular', 'Exercici'])
    .reset_index(drop=True)
)

# ==========================================
# 3. REPORTLAB STYLES & SETUP
# ==========================================
pdf_filename = 'Gym_Complete_Report.pdf'
doc = SimpleDocTemplate(
    pdf_filename,
    pagesize=A4,
    rightMargin=30,
    leftMargin=30,
    topMargin=30,
    bottomMargin=30,
)

styles = getSampleStyleSheet()
title_style = ParagraphStyle(
    'TitleStyle',
    parent=styles['Heading1'],
    fontSize=18,
    leading=22,
    textColor=colors.HexColor('#0F172A'),
)
subtitle_style = ParagraphStyle(
    'SubTitleStyle',
    parent=styles['Normal'],
    fontSize=9,
    textColor=colors.HexColor('#64748B'),
)
cell_style = ParagraphStyle(
    'CellStyle',
    parent=styles['Normal'],
    fontSize=8,
    leading=11,
    textColor=colors.HexColor('#1E293B'),
)
bold_cell = ParagraphStyle('BoldCell', parent=cell_style, fontName='Helvetica-Bold')
blue_cell = ParagraphStyle(
    'BlueCell',
    parent=cell_style,
    fontName='Helvetica-Bold',
    textColor=colors.HexColor('#2563EB'),
)
header_cell = ParagraphStyle(
    'HeaderCell',
    parent=cell_style,
    fontName='Helvetica-Bold',
    textColor=colors.white,
)

elements = []
plt.style.use(
    'seaborn-v0_8-whitegrid'
    if 'seaborn-v0_8-whitegrid' in plt.style.available
    else 'default'
)

# ==========================================
# 4. PART 1: SUMMARY TABLE
# ==========================================
elements.append(Paragraph('Registre de Màxim Volum Diari per Exercici', title_style))
elements.append(
    Paragraph(
        "Resum dels millors registres per exercici (Re-calculat: Pes ×"
        ' Repeticions per sèrie).',
        subtitle_style,
    )
)
elements.append(
    HRFlowable(
        width='100%',
        thickness=1,
        color=colors.HexColor('#E2E8F0'),
        spaceBefore=8,
        spaceAfter=15,
    )
)

table_data = [[
    Paragraph('Exercici', header_cell),
    Paragraph('Grup Muscular', header_cell),
    Paragraph('Data Rècord', header_cell),
    Paragraph('Rècord Màxim', header_cell),
    Paragraph('Detall de Sèries', header_cell),
]]

for _, row in res_table.iterrows():
  table_data.append([
      Paragraph(row['Exercici'], bold_cell),
      Paragraph(row['Grup Muscular'], cell_style),
      Paragraph(row['Data'], cell_style),
      Paragraph(row['Max Record'], blue_cell),
      Paragraph(row['Detall'], cell_style),
  ])

col_widths = [135, 90, 75, 85, 150]
summary_table = Table(table_data, colWidths=col_widths, repeatRows=1)
summary_table.setStyle(
    TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#334155')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        (
            'ROWBACKGROUNDS',
            (0, 1),
            (-1, -1),
            [colors.HexColor('#FFFFFF'), colors.HexColor('#F8FAFC')],
        ),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
    ])
)

elements.append(summary_table)
elements.append(PageBreak())

# ==========================================
# 5. PART 2: PROPORTIONAL PIE CHART (CLEAN LABELS)
# ==========================================
sets_per_mg = df['Grup Muscular'].value_counts()
fig_pie, ax_pie = plt.subplots(figsize=(6, 6), dpi=200)

pie_colors = [
    '#2563EB',
    '#059669',
    '#D97706',
    '#DC2626',
    '#7C3AED',
    '#DB2777',
    '#0D9488',
    '#4F46E5',
]
direct_labels = sets_per_mg.index.tolist()

wedges, texts, autotexts = ax_pie.pie(
    sets_per_mg,
    labels=direct_labels,
    autopct=lambda pct: f'{pct:.1f}%' if pct > 3 else '',
    startangle=140,
    pctdistance=0.65,
    labeldistance=1.1,
    colors=pie_colors[: len(sets_per_mg)],
    wedgeprops=dict(edgecolor='white', linewidth=1.5),
    textprops=dict(fontsize=9, fontweight='bold', color='#1E293B'),
)

plt.setp(autotexts, size=9, weight='bold', color='white')
ax_pie.axis('equal')
ax_pie.set_title(
    'Distribució de Sèries Totals per Grup Muscular (%)',
    fontsize=13,
    fontweight='bold',
    pad=20,
)
plt.tight_layout()

pie_buffer = io.BytesIO()
plt.savefig(pie_buffer, format='png', bbox_inches='tight', dpi=200)
plt.close(fig_pie)
pie_buffer.seek(0)

elements.append(
    Paragraph('Distribució del Volum de Treball (Sèries Totals)', title_style)
)
elements.append(
    Paragraph(
        "Percentatge de sèries totals realitzades per grup muscular per"
        ' avaluar l\'equilibri de la rutina.',
        subtitle_style,
    )
)
elements.append(
    HRFlowable(
        width='100%',
        thickness=1,
        color=colors.HexColor('#E2E8F0'),
        spaceBefore=8,
        spaceAfter=15,
    )
)
elements.append(Image(pie_buffer, width=320, height=320))
elements.append(PageBreak())

# ==========================================
# 6. PART 3: VOLUME PROGRESS LINE GRAPHS (ALL MUSCLE GROUPS)
# ==========================================
graph_daily_df = (
    df.groupby(['Grup Muscular', 'Exercici', 'Data'])
    .agg(
        Max_1RM=('Estimated_1RM', 'max'),
        Daily_Volume=('Set_Volume', 'sum'),
        Daily_Reps=('Repeticions', 'sum'),
        Daily_Time=('Temps (min)', 'sum'),
    )
    .reset_index()
    .sort_values(by='Data')
)

muscle_groups = sorted(graph_daily_df['Grup Muscular'].unique())

for idx, mg in enumerate(muscle_groups):
  mg_data = graph_daily_df[graph_daily_df['Grup Muscular'] == mg]

  fig, ax = plt.subplots(figsize=(8.5, 5), dpi=200)
  exercises = mg_data['Exercici'].unique()

  for ex in exercises:
    ex_data = mg_data[mg_data['Exercici'] == ex]

    if ex_data['Daily_Volume'].sum() > 0:
      y_vals = ex_data['Daily_Volume']
      unit = 'kg'
    elif ex_data['Daily_Reps'].sum() > 0:
      y_vals = ex_data['Daily_Reps']
      unit = 'reps'
    else:
      y_vals = ex_data['Daily_Time']
      unit = 'min'

    ax.plot(
        ex_data['Data'],
        y_vals,
        marker='o',
        linewidth=2,
        markersize=5,
        label=f'{ex} ({unit})',
    )

  ax.set_title(
      f'Evolució de Volum — {mg}', fontsize=12, fontweight='bold', pad=12
  )
  ax.set_xlabel('Data', fontsize=9, labelpad=8)
  ax.set_ylabel('Progrés Diari Total', fontsize=9, labelpad=8)

  ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
  ax.xaxis.set_major_locator(mdates.AutoDateLocator())
  fig.autofmt_xdate()

  ax.grid(True, linestyle='--', alpha=0.5)
  ax.legend(
      title='Exercicis',
      bbox_to_anchor=(1.02, 1),
      loc='upper left',
      frameon=True,
      fontsize=8,
      title_fontsize=8,
  )

  plt.tight_layout()

  img_buffer = io.BytesIO()
  plt.savefig(img_buffer, format='png', bbox_inches='tight', dpi=200)
  plt.close(fig)
  img_buffer.seek(0)

  elements.append(Paragraph(f'Gràfics de Progrés de Volum: {mg}', title_style))
  elements.append(
      Paragraph(
          f"Evolució del volum total per exercici del grup muscular '{mg}' al"
          ' llarg del temps.',
          subtitle_style,
      )
  )
  elements.append(
      HRFlowable(
          width='100%',
          thickness=1,
          color=colors.HexColor('#E2E8F0'),
          spaceBefore=8,
          spaceAfter=15,
      )
  )

  elements.append(Image(img_buffer, width=535, height=315))
  elements.append(PageBreak())

# ==========================================
# 7. PART 4: DEDICATED PAGE FOR 1RM PROGRESSION
# ==========================================
elements.append(Paragraph('Evolució de 1RM Estimat (Exercicis Clau)', title_style))
elements.append(
    Paragraph(
        "Seguiment de la força màxima estimada (Fórmula Brzycki) per a Press Pit"
        ' Mancuerna, Pes Mort, Sentadeta amb Barra i Press Espatlles Mancuerna.',
        subtitle_style,
    )
)
elements.append(
    HRFlowable(
        width='100%',
        thickness=1,
        color=colors.HexColor('#E2E8F0'),
        spaceBefore=8,
        spaceAfter=15,
    )
)

target_1rm_df = graph_daily_df[
    graph_daily_df['Exercici'].isin(TARGET_1RM_EXERCISES)
]

fig_1rm, ax_1rm = plt.subplots(figsize=(8.5, 5.2), dpi=200)

for ex in TARGET_1RM_EXERCISES:
  ex_data = target_1rm_df[target_1rm_df['Exercici'] == ex]
  if not ex_data.empty:
    ax_1rm.plot(
        ex_data['Data'],
        ex_data['Max_1RM'],
        marker='s',
        linewidth=2.5,
        markersize=6,
        label=ex,
    )

ax_1rm.set_title(
    'Evolució del 1RM Estimat (kg)', fontsize=12, fontweight='bold', pad=12
)
ax_1rm.set_xlabel('Data', fontsize=9, labelpad=8)
ax_1rm.set_ylabel('1RM Estimat (kg)', fontsize=9, labelpad=8)

ax_1rm.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
ax_1rm.xaxis.set_major_locator(mdates.AutoDateLocator())
fig_1rm.autofmt_xdate()

ax_1rm.grid(True, linestyle='--', alpha=0.5)
ax_1rm.legend(
    title='Exercicis Clau',
    bbox_to_anchor=(1.02, 1),
    loc='upper left',
    frameon=True,
    fontsize=8,
    title_fontsize=8,
)

plt.tight_layout()

buffer_1rm = io.BytesIO()
plt.savefig(buffer_1rm, format='png', bbox_inches='tight', dpi=200)
plt.close(fig_1rm)
buffer_1rm.seek(0)

elements.append(Image(buffer_1rm, width=535, height=325))

# ==========================================
# 8. BUILD DOCUMENT
# ==========================================
doc.build(elements)
print(f'Report PDF generated successfully: {pdf_filename}')