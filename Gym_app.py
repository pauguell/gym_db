import calendar
import io
import datetime
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from supabase import create_client

# Set Streamlit Page Configuration
st.set_page_config(
    page_title="Gym Performance Dashboard", page_icon="🏋️‍♂️", layout="wide"
)

# -----------------------------------------------------------------------------
# 0. SUPABASE CLIENT CONNECTION
# -----------------------------------------------------------------------------
@st.cache_resource
def init_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_supabase()


# -----------------------------------------------------------------------------
# 1. DATA LOADING & PREPROCESSING (SUPABASE VERSION)
# -----------------------------------------------------------------------------
@st.cache_data
def load_data():
    response = supabase.table("gym_logs").select("*").execute()
    data = response.data
    
    if not data:
        return pd.DataFrame(columns=[
            "id", "Data", "Exercici", "Grup Muscular", "Pes (kg)", 
            "Repeticions", "Temps (min)", "Set_Volume", "Estimated_1RM"
        ])
    
    df = pd.DataFrame(data)

    column_mapping = {
        "id": "id",
        "data": "Data",
        "exercici": "Exercici",
        "grup_muscular": "Grup Muscular",
        "pes_kg": "Pes (kg)",
        "repeticions": "Repeticions",
        "temps_min": "Temps (min)",
    }
    df = df.rename(columns=column_mapping)

    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df["Pes (kg)"] = pd.to_numeric(df["Pes (kg)"], errors="coerce").fillna(0)
    df["Repeticions"] = pd.to_numeric(df["Repeticions"], errors="coerce").fillna(0)
    df["Temps (min)"] = pd.to_numeric(df["Temps (min)"], errors="coerce").fillna(0)

    df = df.dropna(subset=["Exercici", "Data"]).copy()
    df["Exercici"] = df["Exercici"].astype(str).str.strip()
    df["Grup Muscular"] = df["Grup Muscular"].astype(str).str.strip()

    # Set Volume & Estimated 1RM (Brzycki Formula: Weight * 36 / (37 - Reps))
    df["Set_Volume"] = df["Pes (kg)"] * df["Repeticions"]
    df["Estimated_1RM"] = df.apply(
        lambda r: r["Pes (kg)"] * (36 / (37 - r["Repeticions"]))
        if (r["Pes (kg)"] > 0 and 0 < r["Repeticions"] < 37)
        else 0,
        axis=1,
    )
    return df


# -----------------------------------------------------------------------------
# HELPERS: SUPABASE ACTIONS & HEATMAP BUILDER
# -----------------------------------------------------------------------------
def append_set_to_supabase(new_data):
    payload = {
        "data": new_data["Data"],
        "grup_muscular": new_data["Grup Muscular"],
        "exercici": new_data["Exercici"],
        "pes_kg": new_data["Pes (kg)"],
        "repeticions": new_data["Repeticions"],
        "temps_min": new_data["Temps (min)"],
    }
    supabase.table("gym_logs").insert(payload).execute()
    st.cache_data.clear()


def delete_row_from_supabase(row_id):
    supabase.table("gym_logs").delete().eq("id", row_id).execute()
    st.cache_data.clear()


def build_github_heatmap(df):
    """Generates a GitHub-style workout consistency heatmap using Plotly."""
    if df.empty:
        return None

    # Determine date range (past 52 weeks up to latest log or today)
    max_date = df["Data"].max().date()
    min_date = max_date - datetime.timedelta(days=364)

    # Generate full date backbone
    all_dates = pd.date_range(start=min_date, end=max_date, freq="D")
    grid_df = pd.DataFrame({"Data_Dt": all_dates.date})
    grid_df["Data"] = pd.to_datetime(grid_df["Data_Dt"])

    # Aggregate actual user logs per day
    daily_logs = (
        df.groupby(df["Data"].dt.date)
        .agg(
            Total_Volume=("Set_Volume", "sum"),
            Total_Sets=("Set_Volume", "count"),
            Exercises=("Exercici", lambda x: ", ".join(sorted(x.unique()))),
        )
        .reset_index()
        .rename(columns={"Data": "Data_Dt"})
    )

    merged = pd.merge(grid_df, daily_logs, on="Data_Dt", how="left")
    merged["Total_Sets"] = merged["Total_Sets"].fillna(0)
    merged["Total_Volume"] = merged["Total_Volume"].fillna(0)
    merged["Exercises"] = merged["Exercises"].fillna("Descans")

    # Map grid positions (Week Number vs Day of Week)
    merged["Weekday"] = merged["Data"].dt.weekday  # 0=Mon, 6=Sun
    merged["WeekIdx"] = (merged["Data"] - merged["Data"].min()).dt.days // 7

    days_names = ["Dilluns", "Dimarts", "Dimecres", "Dijous", "Divendres", "Dissabte", "Diumenge"]

    # Build matrix for Plotly Heatmap
    pivot_sets = merged.pivot(index="Weekday", columns="WeekIdx", values="Total_Sets").fillna(0)
    pivot_dates = merged.pivot(index="Weekday", columns="WeekIdx", values="Data_Dt")
    pivot_vol = merged.pivot(index="Weekday", columns="WeekIdx", values="Total_Volume").fillna(0)
    pivot_ex = merged.pivot(index="Weekday", columns="WeekIdx", values="Exercises").fillna("Descans")

    # Text hover matrix
    hover_text = []
    for r in range(len(pivot_sets)):
        row_hover = []
        for c in range(len(pivot_sets.columns)):
            raw_date = pivot_dates.iloc[r, c]
            raw_sets = pivot_sets.iloc[r, c]
            raw_vol = pivot_vol.iloc[r, c]
            raw_ex = pivot_ex.iloc[r, c]

            d_str = raw_date.strftime("%d/%m/%Y") if pd.notnull(raw_date) else ""
            sets_val = int(raw_sets) if pd.notnull(raw_sets) else 0
            vol_val = raw_vol if pd.notnull(raw_vol) else 0.0
            ex_val = raw_ex if pd.notnull(raw_ex) else "Descans"

            if sets_val > 0:
                txt = f"<b>📅 {d_str}</b><br>🏋️ Sèries: {sets_val}<br>📦 Volum: {vol_val:,.0f} kg<br>💪 Exercicis: {ex_val}"
            elif d_str:
                txt = f"<b>📅 {d_str}</b><br>😴 Dia de descans"
            else:
                txt = ""
            row_hover.append(txt)
        hover_text.append(row_hover)

    # Custom green colorscale (GitHub-style)
    colorscale = [
        [0.0, "#161b22"],    # Rest / empty day (dark)
        [0.01, "#0e4429"],   # Low activity
        [0.35, "#006d32"],   # Moderate
        [0.70, "#26a641"],   # High
        [1.00, "#39d353"],   # Intense
    ]

    fig = go.Figure(
        data=go.Heatmap(
            z=pivot_sets.values,
            x=pivot_sets.columns,
            y=[days_names[i] for i in pivot_sets.index],
            text=hover_text,
            hoverinfo="text",
            colorscale=colorscale,
            showscale=False,
            xgap=3,
            ygap=3,
        )
    )

    fig.update_layout(
        title="🔥 Calendari de Consistència (Últim Any)",
        height=220,
        margin=dict(l=60, r=10, t=40, b=20),
        yaxis=dict(autorange="reverse", showgrid=False, zeroline=False),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(size=11),
    )

    return fig


# Load Data
df = load_data()

# =============================================================================
# MAIN TITLE
# =============================================================================
st.title("🏋️‍♂️ Interactive Gym Performance Dashboard")
st.markdown("Track set volume, e1RM estimations, duration, reps, and personal records interactively.")

if df.empty:
    st.warning("No data found in Supabase database. Add your first workout below!")

# =============================================================================
# SECTION 1: DATA MANAGEMENT (Collapsed by Default)
# =============================================================================
with st.expander("🛠️ **Section 1: Data Management (Log & Delete)**", expanded=False):
    st.caption("Log new workout sets or search and remove historical log entries.")

    manage_col1, manage_col2 = st.columns(2, gap="large")

    # --- 1A. LOG NEW SET FORM ---
    with manage_col1:
        with st.expander("➕ **Log New Set to Cloud**", expanded=False):
            if not df.empty:
                existing_mg = sorted(df["Grup Muscular"].unique())
            else:
                existing_mg = ["Chest", "Back", "Legs", "Shoulders", "Arms", "Core"]

            selected_log_mg = st.selectbox(
                "Muscle Group", options=existing_mg, key="form_mg_select"
            )

            if not df.empty:
                existing_ex = sorted(
                    df[df["Grup Muscular"] == selected_log_mg]["Exercici"].unique()
                )
            else:
                existing_ex = []

            with st.form("log_set_form", clear_on_submit=False):
                log_date = st.date_input("Date", value=pd.Timestamp.now().date(), key="form_date")

                log_ex_option = st.selectbox(
                    "Exercise", options=existing_ex + ["+ Add New Exercise..."], key="form_ex_select"
                )

                if log_ex_option == "+ Add New Exercise...":
                    log_ex = st.text_input("Enter New Exercise Name", key="form_new_ex_input")
                else:
                    log_ex = log_ex_option

                # Quick-fill helper button logic
                if not df.empty and log_ex_option != "+ Add New Exercise..." and log_ex_option:
                    last_entry_df = df[df["Exercici"] == log_ex_option].sort_values(by="Data", ascending=False)
                    if not last_entry_df.empty:
                        last_row = last_entry_df.iloc[0]
                        default_w = float(last_row["Pes (kg)"])
                        default_r = int(last_row["Repeticions"])
                        default_t = float(last_row["Temps (min)"])
                        st.caption(f"💡 Last logged: {last_row['Data'].strftime('%d/%m/%Y')} → {default_w}kg x {default_r} reps")
                        
                        if st.form_submit_button("⚡ Copy Last Set Values"):
                            st.session_state["prefill_weight"] = default_w
                            st.session_state["prefill_reps"] = default_r
                            st.session_state["prefill_time"] = default_t
                            st.rerun()

                # Fallback values from session state if copied
                def_w = st.session_state.get("prefill_weight", None)
                def_r = st.session_state.get("prefill_reps", None)
                def_t = st.session_state.get("prefill_time", None)

                col_weight, col_reps = st.columns(2)
                with col_weight:
                    log_weight = st.number_input(
                        "Weight (kg)",
                        min_value=0.0,
                        step=0.5,
                        value=def_w,
                        placeholder="0.0",
                    )
                with col_reps:
                    log_reps = st.number_input(
                        "Reps", min_value=0, step=1, value=def_r, format="%d", placeholder="0"
                    )

                log_time = st.number_input(
                    "Duration (min)",
                    min_value=0.0,
                    step=0.5,
                    value=def_t,
                    placeholder="0.0",
                )

                submit_set = st.form_submit_button("💾 Save Set to Cloud")

                if submit_set:
                    final_ex_name = log_ex.strip() if log_ex_option == "+ Add New Exercise..." else log_ex_option
                    if not final_ex_name:
                        st.error("Please enter a valid exercise name.")
                    else:
                        new_entry = {
                            "Data": pd.to_datetime(log_date).strftime("%Y-%m-%d"),
                            "Exercici": final_ex_name,
                            "Grup Muscular": selected_log_mg.strip(),
                            "Pes (kg)": log_weight if log_weight is not None else 0.0,
                            "Repeticions": log_reps if log_reps is not None else 0,
                            "Temps (min)": log_time if log_time is not None else 0.0,
                        }

                        try:
                            append_set_to_supabase(new_entry)
                            st.session_state.pop("prefill_weight", None)
                            st.session_state.pop("prefill_reps", None)
                            st.session_state.pop("prefill_time", None)
                            
                            st.success(f"Saved: {final_ex_name}!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error saving set: {e}")

    # --- 1B. DELETE MISTAKEN ENTRIES ---
    with manage_col2:
        with st.expander("🗑️ **Remove Entry**", expanded=False):
            if not df.empty:
                min_date_val = df["Data"].min().date()
                max_date_val = df["Data"].max().date()
                
                selected_del_date = st.date_input(
                    "Filter by Date",
                    value=max_date_val,
                    min_value=min_date_val,
                    max_value=max_date_val,
                    key="del_single_date_filter"
                )
                
                available_del_ex = sorted(df["Exercici"].unique().tolist())
                selected_del_ex = st.selectbox(
                    "Filter by Exercise",
                    options=["All Exercises"] + available_del_ex,
                    key="del_ex_filter"
                )
                
                del_filtered_df = df[
                    df["Data"].dt.date == selected_del_date
                ].copy()
                
                if selected_del_ex != "All Exercises":
                    del_filtered_df = del_filtered_df[del_filtered_df["Exercici"] == selected_del_ex]
                
                del_filtered_df = del_filtered_df.sort_values(by="Data", ascending=False)
                
                if not del_filtered_df.empty:
                    del_filtered_df["Display_Label"] = (
                        del_filtered_df["Data"].dt.strftime("%d/%m/%Y") + " - " + 
                        del_filtered_df["Exercici"] + " (" + 
                        del_filtered_df["Pes (kg)"].astype(str) + "kg x " + 
                        del_filtered_df["Repeticions"].astype(str) + "r)"
                    )
                    
                    row_to_delete = st.selectbox(
                        "Select entry to remove", 
                        options=del_filtered_df.index, 
                        format_func=lambda x: del_filtered_df.loc[x, "Display_Label"],
                        key="del_row_select"
                    )
                    
                    if st.button("❌ Delete Selected Entry", type="secondary", key="del_btn"):
                        target_id = df.loc[row_to_delete, "id"]
                        try:
                            delete_row_from_supabase(target_id)
                            st.success("Entry deleted successfully!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error deleting entry: {e}")
                else:
                    st.info("No logs match the selected date and exercise.")
            else:
                st.info("No logs available to delete.")

# =============================================================================
# SECTION 2: WORKOUT VISUALIZATION (Collapsed by Default with Heatmap)
# =============================================================================
with st.expander("📋 **Section 2: Visualització d'Entrenament per Dia**", expanded=False):
    st.caption("Consulta el mapa de consistència diari i selecciona una data per veure el desglossament complet de les sèries.")

    if df.empty:
        st.info("No hi ha entrenaments registrats a la base de dades.")
    else:
        # --- NEW: GITHUB-STYLE HEATMAP AT TOP OF SECTION 2 ---
        heatmap_fig = build_github_heatmap(df)
        if heatmap_fig:
            st.plotly_chart(heatmap_fig, use_container_width=True, config={"displayModeBar": False})

        available_dates = pd.to_datetime(df["Data"]).dt.date.unique()
        available_dates = sorted(available_dates, reverse=True)

        selected_date = st.selectbox(
            "📅 Selecciona la Data de l'Entrenament:",
            options=available_dates,
            format_func=lambda d: d.strftime("%d/%m/%Y"),
            key="workout_day_picker"
        )

        df_day = df[pd.to_datetime(df["Data"]).dt.date == selected_date].copy()

        if df_day.empty:
            st.warning(f"No s'han trobat exercicis per al dia {selected_date.strftime('%d/%m/%Y')}.")
        else:
            def format_workout_set(row):
                p = row["Pes (kg)"]
                r = row["Repeticions"]
                t = row["Temps (min)"]

                pes_str = f"{int(p)}" if p == int(p) else f"{p}"
                reps_str = f"{int(r)}" if r == int(r) else f"{r}"
                temps_str = f"{int(t)}" if t == int(t) else f"{t}"

                if t > 0:
                    return f"{temps_str} min" if p == 0 and r == 0 else f"{pes_str} kg x {reps_str} reps ({temps_str} min)"
                return f"{pes_str} kg x {reps_str} reps" if p > 0 else f"{reps_str} reps"

            df_day["Set_Desc"] = df_day.apply(format_workout_set, axis=1)

            total_vol = df_day["Set_Volume"].sum()
            total_sets = len(df_day)
            total_exercises = df_day["Exercici"].nunique()

            mcol1, mcol2, mcol3 = st.columns(3)
            mcol1.metric("🏋️ Exercicis", total_exercises)
            mcol2.metric("🔢 Total Sèries", total_sets)
            mcol3.metric("📦 Volum Total", f"{total_vol:,.0f} kg")

            st.markdown("### 🏋️ Exercicis Realitzats")

            for exercici, ex_group in df_day.groupby("Exercici"):
                grup_muscular = ex_group["Grup Muscular"].iloc[0]
                num_series = len(ex_group)
                
                with st.expander(f"💪 **{exercici}** ({grup_muscular}) — {num_series} sèries", expanded=False):
                    for i, (_, row) in enumerate(ex_group.iterrows()):
                        st.markdown(f"**Sèrie {i+1}:** {row['Set_Desc']}")


# =============================================================================
# SECTION 3: DATA VISUALIZATION & ANALYTICS (Collapsed by Default)
# =============================================================================
with st.expander("📊 **Section 3: Anàlisi i Comparativa**", expanded=False):
    if df.empty:
        st.info("No hi ha dades disponibles per analitzar.")
    else:
        st.subheader("🔍 Filtres Globals")

        all_muscle_groups = sorted(df["Grup Muscular"].dropna().unique().tolist())

        col_f1, col_f2 = st.columns(2)

        with col_f1:
            selected_muscle_groups = st.multiselect(
                "Filtrar per Grup Muscular:",
                options=all_muscle_groups,
                default=[],
                placeholder="Tots els grups (desmarcat)"
            )

        if selected_muscle_groups:
            filtered_exercises_options = sorted(
                df[df["Grup Muscular"].isin(selected_muscle_groups)]["Exercici"].dropna().unique().tolist()
            )
        else:
            filtered_exercises_options = sorted(df["Exercici"].dropna().unique().tolist())

        with col_f2:
            selected_exercises = st.multiselect(
                "Filtrar per Exercici:",
                options=filtered_exercises_options,
                default=[],
                placeholder="Tots els exercicis (desmarcat)"
            )

        df["Data_Dt"] = pd.to_datetime(df["Data"]).dt.date
        min_db_date = df["Data_Dt"].min()
        max_db_date = df["Data_Dt"].max()

        date_range = st.date_input(
            "📅 Ràng de Dates:",
            value=(min_db_date, max_db_date),
            min_value=min_db_date,
            max_value=max_db_date,
            format="DD/MM/YYYY"
        )

        df_filtered = df.copy()

        if selected_muscle_groups:
            df_filtered = df_filtered[df_filtered["Grup Muscular"].isin(selected_muscle_groups)]

        if selected_exercises:
            df_filtered = df_filtered[df_filtered["Exercici"].isin(selected_exercises)]

        if isinstance(date_range, tuple) and len(date_range) == 2:
            start_date, end_date = date_range
            df_filtered = df_filtered[
                (df_filtered["Data_Dt"] >= start_date) & 
                (df_filtered["Data_Dt"] <= end_date)
            ]

        tab1, tab2 = st.tabs([
            "🏆 Rècards i Últims Registres",
            "📈 Evolució de Rendiment"
        ])

        # -------------------------------------------------------------
        # TAB 1: PERSONAL RECORDS & PER-EXERCISE SUMMARY
        # -------------------------------------------------------------
        with tab1:
            if df_filtered.empty:
                st.info("No hi ha dades per als filtres seleccionats.")
            else:
                def format_set(row):
                    p = row["Pes (kg)"]
                    r = row["Repeticions"]
                    t = row["Temps (min)"]

                    pes_str = f"{int(p)}" if p == int(p) else f"{p}"
                    reps_str = f"{int(r)}" if r == int(r) else f"{r}"
                    temps_str = f"{int(t)}" if t == int(t) else f"{t}"

                    if t > 0:
                        return f"{temps_str} min" if p == 0 and r == 0 else f"{pes_str}kg x {reps_str} reps ({temps_str} min)"
                    return f"{pes_str}kg x {reps_str} reps" if p > 0 else f"{reps_str} reps"

                df_tab1 = df_filtered.copy()
                df_tab1["Set_Desc"] = df_tab1.apply(format_set, axis=1)

                st.subheader("⏱️ Últim Entrenament per Exercici")
                st.caption("Detall de les sèries realitzades en l'últim dia d'entrenament registrat.")

                latest_dates = df_filtered.groupby("Exercici")["Data"].max().reset_index()
                last_workout_sets = pd.merge(df_tab1, latest_dates, on=["Exercici", "Data"], how="inner").copy()
                last_workout_sets = last_workout_sets.sort_values(by="Data", ascending=False)

                for ex in last_workout_sets["Exercici"].unique():
                    ex_data = last_workout_sets[last_workout_sets["Exercici"] == ex]
                    mg = ex_data["Grup Muscular"].iloc[0]
                    date_str = pd.to_datetime(ex_data["Data"].iloc[0]).strftime("%d/%m/%Y")
                    
                    with st.expander(f"🏋️ **{ex}** ({mg}) — 📅 {date_str}", expanded=False):
                        for i, (_, row) in enumerate(ex_data.iterrows()):
                            st.markdown(f"**Sèrie {i+1}:** {row['Set_Desc']}")

                st.markdown("---")
                st.subheader("🏆 Dia de Màxim Rendiment per Exercici")
                st.caption("Resum del dia de màxim registre (Volum, Temps o Repeticions).")

                df_tab1["Ex_Type"] = np.where(
                    (df_tab1["Temps (min)"] > 0) & (df_tab1["Set_Volume"] == 0),
                    "Timed",
                    np.where(
                        (df_tab1["Pes (kg)"] == 0) & (df_tab1["Temps (min)"] == 0) & (df_tab1["Repeticions"] > 0),
                        "BW_Reps",
                        "Weighted",
                    ),
                )

                daily_totals = (
                    df_tab1.groupby(["Exercici", "Grup Muscular", "Ex_Type", "Data"])
                    .agg(
                        Daily_Volume=("Set_Volume", "sum"),
                        Daily_Time=("Temps (min)", "sum"),
                        Daily_Reps=("Repeticions", "sum"),
                    )
                    .reset_index()
                )

                daily_totals["Max_Metric_Value"] = np.where(
                    daily_totals["Ex_Type"] == "Timed",
                    daily_totals["Daily_Time"],
                    np.where(
                        daily_totals["Ex_Type"] == "BW_Reps",
                        daily_totals["Daily_Reps"],
                        daily_totals["Daily_Volume"],
                    ),
                )

                max_idx = daily_totals.groupby("Exercici")["Max_Metric_Value"].idxmax()
                max_dates = daily_totals.loc[max_idx]

                max_day_sets = pd.merge(
                    df_tab1,
                    max_dates[["Exercici", "Data"]],
                    on=["Exercici", "Data"],
                    how="inner",
                )
                max_day_sets = max_day_sets.sort_values(by="Data", ascending=False)

                for ex in max_day_sets["Exercici"].unique():
                    ex_data = max_day_sets[max_day_sets["Exercici"] == ex]
                    mg = ex_data["Grup Muscular"].iloc[0]
                    date_str = pd.to_datetime(ex_data["Data"].iloc[0]).strftime("%d/%m/%Y")
                    ex_type = ex_data["Ex_Type"].iloc[0]
                    
                    if ex_type == "Timed":
                        val = ex_data["Temps (min)"].sum()
                        val_str = f"{int(val)} min" if val == int(val) else f"{val:.1f} min"
                    elif ex_type == "BW_Reps":
                        val = ex_data["Repeticions"].sum()
                        val_str = f"{int(val):,} reps"
                    else:
                        val = ex_data["Set_Volume"].sum()
                        val_str = f"{val:,.0f} kg Vol"

                    with st.expander(f"⭐ **{ex}** ({mg}) — 🏆 {val_str} ({date_str})", expanded=False):
                        for i, (_, row) in enumerate(ex_data.iterrows()):
                            st.markdown(f"**Sèrie {i+1}:** {row['Set_Desc']}")

        # -------------------------------------------------------------
        # TAB 2: PROGRESSION CHARTS & ANALYTICS
        # -------------------------------------------------------------
        with tab2:
            st.subheader("📈 Evolució de Rendiment i Volum")
            st.caption("Passa o toca qualsevol punt per veure el desglossament de sèries d'aquell dia.")

            if df_filtered.empty:
                st.info("No hi ha dades disponibles per als filtres seleccionats.")
            else:
                def format_set_hover(row):
                    p = row["Pes (kg)"]
                    r = row["Repeticions"]
                    t = row["Temps (min)"]

                    pes_str = f"{int(p)}" if p == int(p) else f"{p}"
                    reps_str = f"{int(r)}" if r == int(r) else f"{r}"
                    temps_str = f"{int(t)}" if t == int(t) else f"{t}"

                    if t > 0:
                        return f"{temps_str} min" if p == 0 and r == 0 else f"{pes_str}kg x {reps_str} reps ({temps_str} min)"
                    return f"{pes_str}kg x {reps_str} reps" if p > 0 else f"{reps_str} reps"

                df_tab2 = df_filtered.copy()
                df_tab2["Set_Desc"] = df_tab2.apply(format_set_hover, axis=1)

                df_tab2["e1RM"] = np.where(
                    df_tab2["Repeticions"] > 1,
                    df_tab2["Pes (kg)"] / (1.0278 - (0.0278 * df_tab2["Repeticions"])),
                    df_tab2["Pes (kg)"]
                )

                daily_exercise_summary = (
                    df_tab2.groupby(["Data", "Exercici"])
                    .apply(
                        lambda g: pd.Series({
                            "Set_Volume": g["Set_Volume"].sum(),
                            "Max_Pes": g["Pes (kg)"].max(),
                            "Max_e1RM": g["e1RM"].max(),
                            "Set_Details_HTML": "<br>".join([f"Sèrie {i+1}: {row['Set_Desc']}" for i, (_, row) in enumerate(g.iterrows())])
                        })
                    )
                    .reset_index()
                )

                mobile_layout_defaults = dict(
                    margin=dict(l=10, r=10, t=40, b=40),
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=-0.35,
                        xanchor="center",
                        x=0.5
                    ),
                    hovermode="closest",
                    font=dict(size=11)
                )

                # CHART 1: DAILY VOLUME
                fig_vol = px.line(
                    daily_exercise_summary,
                    x="Data",
                    y="Set_Volume",
                    color="Exercici",
                    title="📦 Volum Total Diari (kg)",
                    markers=True,
                    custom_data=["Set_Details_HTML", "Exercici"]
                )

                fig_vol.update_traces(
                    hovertemplate=(
                        "<b>%{customdata[1]}</b><br>" +
                        "📅 %{x|%d/%m/%Y}<br>" +
                        "📦 Volum Total: %{y:,.0f} kg<br>" +
                        "--------------------<br>" +
                        "%{customdata[0]}<extra></extra>"
                    )
                )

                fig_vol.update_layout(**mobile_layout_defaults)
                fig_vol.update_xaxes(title_text="", showgrid=True)
                fig_vol.update_yaxes(title_text="kg")

                st.plotly_chart(fig_vol, use_container_width=True, config={"displayModeBar": False})

                st.markdown("---")

                # CHART 2: STRENGTH METRIC
                metric_choice = st.radio(
                    "Mètrica de Força:",
                    options=["e1RM Estimat", "Pes Màxim Aixecat"],
                    horizontal=True,
                    key="metric_choice_tab2"
                )

                y_col = "Max_e1RM" if metric_choice == "e1RM Estimat" else "Max_Pes"
                y_label = "e1RM Estimat" if metric_choice == "e1RM Estimat" else "Pes Màxim"

                fig_strength = px.line(
                    daily_exercise_summary,
                    x="Data",
                    y=y_col,
                    color="Exercici",
                    title=f"💪 Evolució de Força ({y_label})",
                    markers=True,
                    custom_data=["Set_Details_HTML", "Exercici"]
                )

                fig_strength.update_traces(
                    hovertemplate=(
                        "<b>%{customdata[1]}</b><br>" +
                        "📅 %{x|%d/%m/%Y}<br>" +
                        f"💪 {y_label}: %{{y:.1f}} kg<br>" +
                        "--------------------<br>" +
                        "%{customdata[0]}<extra></extra>"
                    )
                )

                fig_strength.update_layout(**mobile_layout_defaults)
                fig_strength.update_xaxes(title_text="", showgrid=True)
                fig_strength.update_yaxes(title_text="kg")

                st.plotly_chart(fig_strength, use_container_width=True, config={"displayModeBar": False})

                st.markdown("---")

                # CHART 3: TOTAL SETS BY MUSCLE GROUP
                muscle_summary = (
                    df_filtered.groupby("Grup Muscular")
                    .agg(
                        Total_Series=("Set_Volume", "count"),
                        Total_Reps=("Repeticions", "sum")
                    )
                    .reset_index()
                )

                fig_muscle = px.bar(
                    muscle_summary,
                    x="Grup Muscular",
                    y="Total_Series",
                    text="Total_Series",
                    title="📊 Total de Sèries per Grup Muscular",
                    labels={"Total_Series": "Nº de Sèries", "Grup Muscular": "Grup"}
                )
                fig_muscle.update_traces(textposition="outside")
                fig_muscle.update_layout(
                    margin=dict(l=10, r=10, t=40, b=40),
                    font=dict(size=11)
                )
                fig_muscle.update_xaxes(title_text="")
                fig_muscle.update_yaxes(title_text="Sèries")

                st.plotly_chart(fig_muscle, use_container_width=True, config={"displayModeBar": False})