import io
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


# 1. Custom Canvas for Dynamic Page Numbering (Page X of Y)
class NumberedCanvas(canvas.Canvas):

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self._saved_page_states = []

  def showPage(self):
    self._saved_page_states.append(dict(self.__dict__))
    self._startPage()

  def save(self):
    num_pages = len(self._saved_page_states)
    for state in self._saved_page_states:
      self.__dict__.update(state)
      self.draw_page_number(num_pages)
      canvas.Canvas.showPage(self)
    canvas.Canvas.save(self)

  def draw_page_number(self, page_count):
    self.saveState()
    self.setFont('Helvetica', 8)
    self.setFillColor(colors.HexColor('#64748B'))

    # Draw footer text and top stroke line
    footer_text = (
        f'Gym Performance Report  |  Page {self._pageNumber} of {page_count}'
    )
    self.drawRightString(A4[0] - 30, 20, footer_text)
    self.drawString(30, 20, 'Confidential & Personal Fitness Tracker')
    self.setStrokeColor(colors.HexColor('#E2E8F0'))
    self.setLineWidth(0.5)
    self.line(30, 32, A4[0] - 30, 32)
    self.restoreState()


# 2. Data Loading & Cleaning
file_path = 'Gym_Registre_PG.xlsx'
df = pd.read_excel(file_path, sheet_name='Registre_Exercicis', header=3)

df['Data'] = pd.to_datetime(df['Data'], errors='coerce')
df['Pes (kg)'] = pd.to_numeric(df['Pes (kg)'], errors='coerce').fillna(0)
df['Repeticions'] = pd.to_numeric(df['Repeticions'], errors='coerce').fillna(0)
df['Temps (min)'] = pd.to_numeric(df['Temps (min)'], errors='coerce').fillna(0)

df = df.dropna(subset=['Exercici', 'Data']).copy()
df['Exercici'] = df['Exercici'].astype(str).str.strip()
df['Grup Muscular'] = df['Grup Muscular'].astype(str).str.strip()

# Volume & Estimated 1RM Calculations
df['Set_Volume'] = df['Pes (kg)'] * df['Repeticions']
df['Estimated_1RM'] = df.apply(
    lambda r: r['Pes (kg)'] * (36 / (37 - r['Repeticions']))
    if (r['Pes (kg)'] > 0 and 0 < r['Repeticions'] < 37)
    else 0,
    axis=1,
)

TARGET_1RM_EXERCISES = [
    'Press Pit Mancuerna',
    'Pes Mort',
    'Sentadeta amb Barra',
    'Press Espatlles Mancuerna',
]

# Daily records aggregation
daily_records = []
for (ex, dt), group in df.groupby(['Exercici', 'Data']):
  mg = group['Grup Muscular'].iloc[0]
  total_vol = group['Set_Volume'].sum()
  total_time = group['Temps (min)'].sum()
  total_reps = group['Repeticions'].sum()
  max_1rm = group['Estimated_1RM'].max()
  num_sets = len(group)

  daily_records.append({
      'Exercici': ex,
      'Grup Muscular': mg,
      'Data': dt,
      'Daily_Volume_kg': total_vol,
      'Daily_Time_min': total_time,
      'Daily_Reps': total_reps,
      'Max_Estimated_1RM': max_1rm,
      'Num_Sets': num_sets,
      'Weights_List': group['Pes (kg)'].tolist(),
      'Reps_List': group['Repeticions'].tolist(),
      'Times_List': group['Temps (min)'].tolist(),
  })

table_daily_df = pd.DataFrame(daily_records)

# Summary table data preparation
final_rows = []
for ex, group in table_daily_df.groupby('Exercici'):
  max_vol = group['Daily_Volume_kg'].max()
  max_time = group['Daily_Time_min'].max()
  max_reps = group['Daily_Reps'].max()

  if max_vol == 0 and max_time > 0:
    best_row = group[group['Daily_Time_min'] == max_time].iloc[-1]
    max_rec_str = f"{best_row['Daily_Time_min']:g} min"
    series_desc = [
        f'Sèrie {idx+1}: {t:g} min'
        for idx, t in enumerate(best_row['Times_List'])
    ]
  elif max_vol == 0 and max_reps > 0:
    best_row = group[group['Daily_Reps'] == max_reps].iloc[-1]
    max_rec_str = f"{best_row['Daily_Reps']:g} reps"
    series_desc = [
        f'Sèrie {idx+1}: {r:g} reps'
        for idx, r in enumerate(best_row['Reps_List'])
    ]
  else:
    best_row = group[group['Daily_Volume_kg'] == max_vol].iloc[-1]
    max_rec_str = f"{best_row['Daily_Volume_kg']:g} kg"
    series_desc = [
        f'Sèrie {idx+1}: {w:g}kg, {r:g} reps' if w > 0 else f'Sèrie {idx+1}: {r:g} reps'
        for idx, (w, r) in enumerate(
            zip(best_row['Weights_List'], best_row['Reps_List'])
        )
    ]

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

# KPI Metrics
total_workouts = df['Data'].nunique()
total_tonnage = df['Set_Volume'].sum()
total_sets = len(df)
total_exercises = df['Exercici'].nunique()

# 3. ReportLab Document Setup & Styling
pdf_filename = 'Gym_Polished_Report.pdf'
doc = SimpleDocTemplate(
    pdf_filename,
    pagesize=A4,
    rightMargin=30,
    leftMargin=30,
    topMargin=35,
    bottomMargin=45,
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
kpi_title_style = ParagraphStyle(
    'KPITitle',
    fontName='Helvetica-Bold',
    fontSize=8,
    leading=10,
    textColor=colors.HexColor('#475569'),
    alignment=1,
)
kpi_val_style = ParagraphStyle(
    'KPIVal',
    fontName='Helvetica-Bold',
    fontSize=14,
    leading=16,
    textColor=colors.HexColor('#2563EB'),
    alignment=1,
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

# --- PAGE 1: HEADER & KPI DASHBOARD & SUMMARY TABLE ---
elements.append(
    Paragraph('Informe Executive de Rendiment de Gimnàs', title_style)
)
elements.append(
    Paragraph(
        "Resum estadístic global i anàlisi detallada del progrés d'entrenament",
        subtitle_style,
    )
)
elements.append(
    HRFlowable(
        width='100%',
        thickness=1,
        color=colors.HexColor('#CBD5E1'),
        spaceBefore=8,
        spaceAfter=12,
    )
)

# KPI Summary Cards
kpi_data = [
    [
        Paragraph('SESSIONS TOTALS', kpi_title_style),
        Paragraph('TONATGE TOTAL', kpi_title_style),
        Paragraph('SÈRIES REGISTRADES', kpi_title_style),
        Paragraph('EXERCICIS ACTIUS', kpi_title_style),
    ],
    [
        Paragraph(f'{total_workouts}', kpi_val_style),
        Paragraph(f'{total_tonnage:,.0f} kg', kpi_val_style),
        Paragraph(f'{total_sets}', kpi_val_style),
        Paragraph(f'{total_exercises}', kpi_val_style),
    ],
]

kpi_table = Table(kpi_data, colWidths=[133, 134, 134, 134])
kpi_table.setStyle(
    TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F1F5F9')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#E2E8F0')),
        ('INNERGRID', (0, 0), (-1, -1), 1, colors.HexColor('#E2E8F0')),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ])
)
elements.append(kpi_table)
elements.append(Spacer(1, 15))

# Summary Table
elements.append(
    Paragraph(
        'Registre de Màxim Volum Diari per Exercici',
        ParagraphStyle(
            'SubHead',
            parent=styles['Heading2'],
            fontSize=12,
            leading=15,
            textColor=colors.HexColor('#1E293B'),
        ),
    )
)
elements.append(Spacer(1, 5))

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

summary_table = Table(table_data, colWidths=[130, 85, 75, 85, 160], repeatRows=1)
summary_table.setStyle(
    TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E293B')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
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

# --- PAGE 2: PIE CHART ---
sets_per_mg = df['Grup Muscular'].value_counts()
fig_pie, ax_pie = plt.subplots(figsize=(6, 5), dpi=200)

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
wedges, texts, autotexts = ax_pie.pie(
    sets_per_mg,
    labels=sets_per_mg.index.tolist(),
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
    fontsize=12,
    fontweight='bold',
    pad=15,
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
        "Percentatge de sèries totals realitzades per grup muscular per avaluar"
        " l'equilibri de la rutina.",
        subtitle_style,
    )
)
elements.append(
    HRFlowable(
        width='100%',
        thickness=1,
        color=colors.HexColor('#CBD5E1'),
        spaceBefore=8,
        spaceAfter=15,
    )
)
elements.append(Image(pie_buffer, width=350, height=290))
elements.append(PageBreak())

# --- PAGE 3: COMPACT 2-COLUMN VOLUME GRAPHS ---
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
mg_images = []

for mg in muscle_groups:
  mg_data = graph_daily_df[graph_daily_df['Grup Muscular'] == mg]
  fig, ax = plt.subplots(figsize=(4.2, 3.2), dpi=200)

  for ex in mg_data['Exercici'].unique():
    ex_data = mg_data[mg_data['Exercici'] == ex]
    if ex_data['Daily_Volume'].sum() > 0:
      y_vals, unit = ex_data['Daily_Volume'], 'kg'
    elif ex_data['Daily_Reps'].sum() > 0:
      y_vals, unit = ex_data['Daily_Reps'], 'reps'
    else:
      y_vals, unit = ex_data['Daily_Time'], 'min'

    ax.plot(
        ex_data['Data'],
        y_vals,
        marker='o',
        linewidth=1.5,
        markersize=3.5,
        label=f'{ex} ({unit})',
    )

  ax.set_title(f'Volum: {mg}', fontsize=9, fontweight='bold', pad=6)
  ax.set_ylabel('Progrés Diari Total', fontsize=7)
  ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
  ax.xaxis.set_major_locator(mdates.AutoDateLocator())
  ax.tick_params(axis='both', which='major', labelsize=7)
  fig.autofmt_xdate()
  ax.grid(True, linestyle='--', alpha=0.5)
  ax.legend(loc='upper left', frameon=True, fontsize=6)
  plt.tight_layout()

  buf = io.BytesIO()
  plt.savefig(buf, format='png', bbox_inches='tight', dpi=200)
  plt.close(fig)
  buf.seek(0)
  mg_images.append(Image(buf, width=260, height=198))

elements.append(
    Paragraph('Evolució de Volum per Grup Muscular', title_style)
)
elements.append(
    Paragraph(
        'Seguiment del volum total o repeticions realitzades agrupats per zona'
        ' muscular.',
        subtitle_style,
    )
)
elements.append(
    HRFlowable(
        width='100%',
        thickness=1,
        color=colors.HexColor('#CBD5E1'),
        spaceBefore=8,
        spaceAfter=15,
    )
)

# Render graphs side-by-side in 2 columns
for i in range(0, len(mg_images), 2):
  row_imgs = mg_images[i : i + 2]
  if len(row_imgs) == 1:
    row_imgs.append(Paragraph('', cell_style))

  table_grid = Table([row_imgs], colWidths=[265, 265])
  table_grid.setStyle(
      TableStyle([
          ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
          ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
          ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
      ])
  )
  elements.append(table_grid)
  if (i + 2) % 4 == 0 and (i + 2) < len(mg_images):
    elements.append(PageBreak())

elements.append(PageBreak())

# --- PAGE 4: 1RM TRENDS WITH MOVING AVERAGE & PEAKS ---
elements.append(
    Paragraph('Evolució de 1RM Estimat + Tendència (MA)', title_style)
)
elements.append(
    Paragraph(
        'Força màxima estimada (Brzycki) amb línia de tendència de mitjana'
        ' mòbil (3 sessions) i indicació del rècord absolut (★).',
        subtitle_style,
    )
)
elements.append(
    HRFlowable(
        width='100%',
        thickness=1,
        color=colors.HexColor('#CBD5E1'),
        spaceBefore=8,
        spaceAfter=12,
    )
)

fig_1rm, axes = plt.subplots(2, 2, figsize=(8.5, 6.2), dpi=200)
axes = axes.flatten()
target_1rm_df = graph_daily_df[
    graph_daily_df['Exercici'].isin(TARGET_1RM_EXERCISES)
]
plot_colors = ['#2563EB', '#D97706', '#059669', '#DC2626']

for idx, ex in enumerate(TARGET_1RM_EXERCISES):
  ax = axes[idx]
  ex_data = target_1rm_df[target_1rm_df['Exercici'] == ex].sort_values('Data')

  if not ex_data.empty:
    # 3-session Moving Average calculation
    ex_data['MA3'] = ex_data['Max_1RM'].rolling(window=3, min_periods=1).mean()

    # Raw 1RM points
    ax.plot(
        ex_data['Data'],
        ex_data['Max_1RM'],
        marker='o',
        linewidth=1,
        markersize=3,
        color='#94A3B8',
        linestyle=':',
        label='1RM Diari',
    )

    # MA Trendline
    ax.plot(
        ex_data['Data'],
        ex_data['MA3'],
        linewidth=2,
        color=plot_colors[idx % len(plot_colors)],
        label='Tendència (MA 3)',
    )

    # Highlight Peak Record (Star Marker)
    peak_row = ex_data.loc[ex_data['Max_1RM'].idxmax()]
    ax.scatter(
        [peak_row['Data']],
        [peak_row['Max_1RM']],
        color='#F59E0B',
        s=70,
        zorder=5,
        marker='*',
        label=f"Peak: {peak_row['Max_1RM']:.1f}kg",
    )

  ax.set_title(ex, fontsize=10, fontweight='bold', pad=6)
  ax.set_ylabel('1RM Estimat (kg)', fontsize=8)
  ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
  ax.xaxis.set_major_locator(mdates.AutoDateLocator())
  ax.tick_params(axis='both', which='major', labelsize=8)
  ax.grid(True, linestyle='--', alpha=0.5)
  ax.legend(loc='lower right', fontsize=6.5, frameon=True)

fig_1rm.autofmt_xdate()
plt.tight_layout()

buffer_1rm = io.BytesIO()
plt.savefig(buffer_1rm, format='png', bbox_inches='tight', dpi=200)
plt.close(fig_1rm)
buffer_1rm.seek(0)

elements.append(Image(buffer_1rm, width=535, height=390))

# Build Document
doc.build(elements, canvasmaker=NumberedCanvas)
print("PDF 'Gym_Polished_Report.pdf' successfully generated!")