import datetime
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from supabase import create_client

# Set Streamlit Page Configuration
st.set_page_config(
    page_title="Gimnàs - Menú de Rendiment",
    page_icon="🏋️‍♂️",
    layout="wide",
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
# 1. DATA LOADING & PREPROCESSING
# -----------------------------------------------------------------------------
@st.cache_data
def load_data():
    """Fetches gym logs from Supabase and applies vectorized preprocessing."""
    response = supabase.table("gym_logs").select("*").execute()
    data = response.data

    if not data:
        return pd.DataFrame(
            columns=[
                "id",
                "Data",
                "Exercici",
                "Grup Muscular",
                "Pes (kg)",
                "Repeticions",
                "Temps (min)",
                "Set_Volume",
                "Estimated_1RM",
            ]
        )

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
    df["Pes (kg)"] = pd.to_numeric(df["Pes (kg)"], errors="coerce").fillna(0.0)
    df["Repeticions"] = (
        pd.to_numeric(df["Repeticions"], errors="coerce").fillna(0).astype(int)
    )
    df["Temps (min)"] = (
        pd.to_numeric(df["Temps (min)"], errors="coerce").fillna(0.0)
    )

    df = df.dropna(subset=["Exercici", "Data"]).copy()
    df["Exercici"] = df["Exercici"].astype(str).str.strip()
    df["Grup Muscular"] = df["Grup Muscular"].astype(str).str.strip()

    # Vectorized Metrics Calculation
    df["Set_Volume"] = df["Pes (kg)"] * df["Repeticions"]

    # Unified Brzycki 1RM Formula: Weight * 36 / (37 - Reps) [Reps < 37]
    valid_1rm_mask = (df["Pes (kg)"] > 0) & (
        df["Repeticions"].between(1, 36, inclusive="both")
    )
    df["Estimated_1RM"] = 0.0
    df.loc[valid_1rm_mask, "Estimated_1RM"] = df.loc[
        valid_1rm_mask, "Pes (kg)"
    ] * (36 / (37 - df.loc[valid_1rm_mask, "Repeticions"]))

    return df


# -----------------------------------------------------------------------------
# 2. SUPABASE DB ACTIONS
# -----------------------------------------------------------------------------
def append_set_to_supabase(new_data):
    """Inserts a new set log into Supabase and clears local cache."""
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
    """Deletes a log entry by primary ID and clears local cache."""
    supabase.table("gym_logs").delete().eq("id", row_id).execute()
    st.cache_data.clear()


# -----------------------------------------------------------------------------
# 3. HEATMAP BUILDER (Scatter Square Calendar)
# -----------------------------------------------------------------------------
def build_github_heatmap(df, selected_period):
    """Generates a Monthly Workout Consistency Heatmap with mobile responsive sizing

    and the 10-tier intensity spectrum.
    """
    if df.empty or not selected_period:
        return None

    # Global max volume reference for scaling intensity
    daily_sets_all_time = df.groupby(df["Data"].dt.date)["Set_Volume"].count()
    max_all_time_sets = (
        int(daily_sets_all_time.max()) if not daily_sets_all_time.empty else 1
    )

    df_month = df[df["Data"].dt.to_period("M") == selected_period].copy()

    start_date = selected_period.to_timestamp().date()
    if start_date.month == 12:
        end_date = datetime.date(start_date.year, 12, 31)
    else:
        end_date = datetime.date(
            start_date.year, start_date.month + 1, 1
        ) - datetime.timedelta(days=1)

    all_dates = pd.date_range(start=start_date, end=end_date, freq="D")
    grid_df = pd.DataFrame({"Data_Dt": all_dates.date})
    grid_df["Data"] = pd.to_datetime(grid_df["Data_Dt"])

    daily_logs = (
        df_month.groupby(df_month["Data"].dt.date)
        .agg(
            Total_Volume=("Set_Volume", "sum"),
            Total_Sets=("Set_Volume", "count"),
        )
        .reset_index()
        .rename(columns={"Data": "Data_Dt"})
    )

    merged = pd.merge(grid_df, daily_logs, on="Data_Dt", how="left")
    merged["Total_Sets"] = merged["Total_Sets"].fillna(0)
    merged["Weekday"] = merged["Data"].dt.weekday

    first_weekday = start_date.weekday()
    merged["MonthWeekIdx"] = (merged["Data"].dt.day + first_weekday - 1) // 7

    days_names = ["Dil", "Dim", "Dmc", "Dij", "Div", "Dis", "Diu"]
    max_weeks = int(merged["MonthWeekIdx"].max() + 1)
    week_labels = [f"S{w + 1}" for w in range(max_weeks)]

    x_vals, y_vals, text_vals, custom_vals, color_vals = [], [], [], [], []

    for _, row in merged.iterrows():
        w_idx = int(row["MonthWeekIdx"])
        d_idx = int(row["Weekday"])
        day_num = row["Data"].day
        sets_val = int(row["Total_Sets"])
        iso_str = row["Data_Dt"].strftime("%Y-%m-%d")

        x_vals.append(days_names[d_idx])
        y_vals.append(week_labels[w_idx])
        text_vals.append(str(day_num))
        custom_vals.append(iso_str)
        color_vals.append(sets_val)

    # 10-Tier Spectrum Heatmap Colorscale
    colorscale = [
        [0.00, "#f8fafc"],  # Rest Day
        [0.10, "#1d4ed8"],  # 10% - Deep Blue
        [0.20, "#3b82f6"],  # 20% - Blue
        [0.30, "#06b6d4"],  # 30% - Cyan
        [0.40, "#5eead4"],  # 40% - Mint
        [0.50, "#86efac"],  # 50% - Soft Green
        [0.60, "#d9f99d"],  # 60% - Lime Green
        [0.70, "#fde047"],  # 70% - Yellow
        [0.80, "#f97316"],  # 80% - Orange
        [0.90, "#ea580c"],  # 90% - Deep Orange
        [1.00, "#dc2626"],  # 100%+ Peak Red
    ]

    fig = go.Figure(
        data=go.Scatter(
            x=x_vals,
            y=y_vals,
            mode="markers+text",
            marker=dict(
                symbol="square",
                size=36,
                sizemode="diameter",
                color=color_vals,
                colorscale=colorscale,
                cmin=0,
                cmax=max_all_time_sets,
                showscale=False,
                line=dict(width=1, color="#cbd5e1"),
            ),
            text=text_vals,
            textposition="middle center",
            textfont=dict(size=11, color="#0f172a", family="Arial Black"),
            customdata=custom_vals,
            hoverinfo="none",
        )
    )

    month_name = start_date.strftime("%B %Y").capitalize()

    fig.update_layout(
        title=dict(
            text=f"📅 {month_name}", y=0.98, x=0.01, xanchor="left", yanchor="top"
        ),
        height=160 + (max_weeks * 40),
        margin=dict(l=30, r=10, t=45, b=10),
        yaxis=dict(
            autorange="reversed",
            showgrid=False,
            zeroline=False,
            fixedrange=True,
            categoryorder="array",
            categoryarray=week_labels,
        ),
        xaxis=dict(
            showgrid=False,
            zeroline=False,
            side="top",
            fixedrange=True,
            categoryorder="array",
            categoryarray=days_names,
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(size=11),
        clickmode="event+select",
    )

    return fig


# Helper String Formatter
def format_workout_set(row):
    p, r, t = row.get("Pes (kg)", 0), row.get("Repeticions", 0), row.get("Temps (min)", 0)
    pes_str = f"{int(p)}" if p == int(p) else f"{p}"
    reps_str = f"{int(r)}" if r == int(r) else f"{r}"
    temps_str = f"{int(t)}" if t == int(t) else f"{t}"

    if t > 0:
        return (
            f"{temps_str} min"
            if p == 0 and r == 0
            else f"{pes_str} kg x {reps_str} reps ({temps_str} min)"
        )
    return f"{pes_str} kg x {reps_str} reps" if p > 0 else f"{reps_str} reps"


# Load Main Data
df = load_data()

# =============================================================================
# MAIN HEADER
# =============================================================================
st.title("🏋️‍♂️ Menú de Rendiment de Gimnàs")
st.markdown(
    "Control de volum de sèries, estimació d'1RM, durada i històric de rècards visuals."
)

if df.empty:
    st.warning(
        "No s'han trobat dades a la base de dades. Afegeix el teu primer entrenament a sota!"
    )

# =============================================================================
# SECTION 1: DATA MANAGEMENT
# =============================================================================
with st.expander("🛠️ **Secció 1: Gestió de Dades (Registrar i Eliminar)**", expanded=False):
    st.caption("Registra noves sèries o cerca i elimina entradors històrics.")

    manage_col1, manage_col2 = st.columns(2, gap="large")

    # --- 1A. LOG NEW SET FORM ---
    with manage_col1:
        with st.expander("➕ **Registrar Nova Sèrie al Núvol**", expanded=False):
            existing_mg = (
                sorted(df["Grup Muscular"].unique())
                if not df.empty
                else ["Pit", "Esquena", "Cames", "Espatlles", "Braços", "Core"]
            )

            selected_log_mg = st.selectbox(
                "Grup Muscular", options=existing_mg, key="form_mg_select"
            )

            existing_ex = (
                sorted(df[df["Grup Muscular"] == selected_log_mg]["Exercici"].unique())
                if not df.empty
                else []
            )

            with st.form("log_set_form", clear_on_submit=False):
                log_date = st.date_input(
                    "Data", value=pd.Timestamp.now().date(), key="form_date"
                )

                log_ex_option = st.selectbox(
                    "Exercici",
                    options=existing_ex + ["+ Afegir Nou Exercici..."],
                    key="form_ex_select",
                )

                if log_ex_option == "+ Afegir Nou Exercici...":
                    log_ex = st.text_input(
                        "Nom del Nou Exercici", key="form_new_ex_input"
                    )
                else:
                    log_ex = log_ex_option

                # Prefill helper
                if (
                    not df.empty
                    and log_ex_option != "+ Afegir Nou Exercici..."
                    and log_ex_option
                ):
                    last_entry_df = df[df["Exercici"] == log_ex_option].sort_values(
                        by="Data", ascending=False
                    )
                    if not last_entry_df.empty:
                        last_row = last_entry_df.iloc[0]
                        default_w = float(last_row["Pes (kg)"])
                        default_r = int(last_row["Repeticions"])
                        default_t = float(last_row["Temps (min)"])
                        st.caption(
                            f"💡 Últim registre: {last_row['Data'].strftime('%d/%m/%Y')} → {default_w}kg x {default_r} reps"
                        )

                        if st.form_submit_button("⚡ Copiar Valors de l'Última Sèrie"):
                            st.session_state["prefill_weight"] = default_w
                            st.session_state["prefill_reps"] = default_r
                            st.session_state["prefill_time"] = default_t
                            st.rerun()

                def_w = st.session_state.get("prefill_weight", None)
                def_r = st.session_state.get("prefill_reps", None)
                def_t = st.session_state.get("prefill_time", None)

                col_weight, col_reps = st.columns(2)
                with col_weight:
                    log_weight = st.number_input(
                        "Pes (kg)",
                        min_value=0.0,
                        step=0.5,
                        value=def_w,
                        placeholder="0.0",
                    )
                with col_reps:
                    log_reps = st.number_input(
                        "Repeticions",
                        min_value=0,
                        step=1,
                        value=def_r,
                        format="%d",
                        placeholder="0",
                    )

                log_time = st.number_input(
                    "Durada (min)",
                    min_value=0.0,
                    step=0.5,
                    value=def_t,
                    placeholder="0.0",
                )

                submit_set = st.form_submit_button("💾 Desar Sèrie al Núvol")

                if submit_set:
                    final_ex_name = (
                        log_ex.strip()
                        if log_ex_option == "+ Afegir Nou Exercici..."
                        else log_ex_option
                    )
                    if not final_ex_name:
                        st.error("Si us plau, introdueix un nom d'exercici vàlid.")
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

                            st.success(f"Desat amb èxit: {final_ex_name}!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error en desar la sèrie: {e}")

    # --- 1B. DELETE MISTAKEN ENTRIES ---
    with manage_col2:
        with st.expander("🗑️ **Eliminar Registre**", expanded=False):
            if not df.empty:
                min_date_val = df["Data"].min().date()
                max_date_val = df["Data"].max().date()

                selected_del_date = st.date_input(
                    "Filtrar per Data",
                    value=max_date_val,
                    min_value=min_date_val,
                    max_value=max_date_val,
                    key="del_single_date_filter",
                )

                available_del_ex = sorted(df["Exercici"].unique().tolist())
                selected_del_ex = st.selectbox(
                    "Filtrar per Exercici",
                    options=["Tots els exercicis"] + available_del_ex,
                    key="del_ex_filter",
                )

                del_filtered_df = df[df["Data"].dt.date == selected_del_date].copy()

                if selected_del_ex != "Tots els exercicis":
                    del_filtered_df = del_filtered_df[
                        del_filtered_df["Exercici"] == selected_del_ex
                    ]

                del_filtered_df = del_filtered_df.sort_values(
                    by="Data", ascending=False
                )

                if not del_filtered_df.empty:
                    del_filtered_df["Display_Label"] = (
                        del_filtered_df["Data"].dt.strftime("%d/%m/%Y")
                        + " - "
                        + del_filtered_df["Exercici"]
                        + " ("
                        + del_filtered_df["Pes (kg)"].astype(str)
                        + "kg x "
                        + del_filtered_df["Repeticions"].astype(str)
                        + "r)"
                    )

                    row_to_delete = st.selectbox(
                        "Selecciona el registre a eliminar",
                        options=del_filtered_df.index,
                        format_func=lambda x: del_filtered_df.loc[x, "Display_Label"],
                        key="del_row_select",
                    )

                    if st.button(
                        "❌ Eliminar Registre Seleccionat",
                        type="secondary",
                        key="del_btn",
                    ):
                        target_id = df.loc[row_to_delete, "id"]
                        try:
                            delete_row_from_supabase(target_id)
                            st.success("Registre eliminat amb èxit!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error en eliminar el registre: {e}")
                else:
                    st.info(
                        "No hi ha registres que coincideixin amb la data i exercici seleccionats."
                    )
            else:
                st.info("No hi ha registres disponibles per eliminar.")

# =============================================================================
# SECTION 2: WORKOUT VISUALIZATION (Interactive Heatmap)
# =============================================================================
with st.expander("📋 **Secció 2: Visualització d'Entrenament per Dia**", expanded=False):
    st.caption(
        "Toca o fes clic en qualsevol dia del calendari per veure el desglossament de l'entrenament a sota."
    )

    if df.empty:
        st.info("No hi ha entrenaments registrats a la base de dades.")
    else:
        df["Data_dt"] = pd.to_datetime(df["Data"])
        df["YearMonth"] = df["Data_dt"].dt.to_period("M")
        available_months = sorted(df["YearMonth"].unique(), reverse=True)

        selected_month_period = st.selectbox(
            "📆 Selecciona el Mes per al Calendari:",
            options=available_months,
            format_func=lambda m: m.strftime("%B %Y").capitalize(),
            key="heatmap_month_picker",
        )

        start_date = selected_month_period.to_timestamp().date()
        if start_date.month == 12:
            end_date = datetime.date(start_date.year, 12, 31)
        else:
            end_date = datetime.date(
                start_date.year, start_date.month + 1, 1
            ) - datetime.timedelta(days=1)

        all_month_dates = sorted(pd.date_range(start_date, end_date).date, reverse=True)

        if (
            "selected_workout_date" not in st.session_state
            or st.session_state["selected_workout_date"] not in all_month_dates
        ):
            st.session_state["selected_workout_date"] = all_month_dates[0]

        heatmap_fig = build_github_heatmap(df, selected_month_period)

        selected_event = None
        if heatmap_fig:
            selected_event = st.plotly_chart(
                heatmap_fig,
                use_container_width=True,
                config={"displayModeBar": False},
                on_select="rerun",
                selection_mode="points",
                key="calendar_heatmap_chart",
            )

        # Sync click event to session_state
        if (
            selected_event
            and "selection" in selected_event
            and selected_event["selection"].get("points")
        ):
            points = selected_event["selection"]["points"]
            if len(points) > 0:
                raw_cd = points[0].get("customdata")
                if raw_cd:
                    clicked_date_str = (
                        raw_cd[0] if isinstance(raw_cd, list) else str(raw_cd)
                    )
                    try:
                        clicked_date_obj = datetime.datetime.strptime(
                            clicked_date_str, "%Y-%m-%d"
                        ).date()
                        if (
                            clicked_date_obj in all_month_dates
                            and st.session_state["selected_workout_date"]
                            != clicked_date_obj
                        ):
                            st.session_state["selected_workout_date"] = clicked_date_obj
                            st.rerun()
                    except ValueError:
                        pass

        st.markdown("---")

        selected_date = st.session_state["selected_workout_date"]
        df_day = df[df["Data_dt"].dt.date == selected_date].copy()

        if df_day.empty:
            st.info(
                f"😴 **{selected_date.strftime('%d/%m/%Y')}** és un dia de descans (sense entrenaments registrats)."
            )
        else:
            df_day["Set_Desc"] = df_day.apply(format_workout_set, axis=1)

            total_vol = df_day["Set_Volume"].sum()
            total_sets = len(df_day)
            total_exercises = df_day["Exercici"].nunique()

            mcol1, mcol2, mcol3 = st.columns(3)
            mcol1.metric("🏋️ Exercicis", total_exercises)
            mcol2.metric("🔢 Total Sèries", total_sets)
            mcol3.metric("📦 Volum Total", f"{total_vol:,.0f} kg")

            st.markdown(
                f"### 🏋️ Exercicis Realitzats ({selected_date.strftime('%d/%m/%Y')})"
            )

            for exercici, ex_group in df_day.groupby("Exercici"):
                grup_muscular = ex_group["Grup Muscular"].iloc[0]
                num_series = len(ex_group)

                with st.expander(
                    f"💪 **{exercici}** ({grup_muscular}) — {num_series} sèries",
                    expanded=False,
                ):
                    for i, (_, row) in enumerate(ex_group.iterrows()):
                        st.markdown(f"**Sèrie {i+1}:** {row['Set_Desc']}")

# =============================================================================
# SECTION 3: DATA VISUALIZATION & ANALYTICS
# =============================================================================
with st.expander("📊 **Secció 3: Anàlisi i Comparativa**", expanded=False):
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
                placeholder="Tots els grups (desmarcat)",
            )

        if selected_muscle_groups:
            filtered_exercises_options = sorted(
                df[df["Grup Muscular"].isin(selected_muscle_groups)][
                    "Exercici"
                ]
                .dropna()
                .unique()
                .tolist()
            )
        else:
            filtered_exercises_options = sorted(
                df["Exercici"].dropna().unique().tolist()
            )

        with col_f2:
            selected_exercises = st.multiselect(
                "Filtrar per Exercici:",
                options=filtered_exercises_options,
                default=[],
                placeholder="Tots els exercicis (desmarcat)",
            )

        df["Data_Dt"] = pd.to_datetime(df["Data"]).dt.date
        min_db_date = df["Data_Dt"].min()
        max_db_date = df["Data_Dt"].max()

        date_range = st.date_input(
            "📅 Ràng de Dates:",
            value=(min_db_date, max_db_date),
            min_value=min_db_date,
            max_value=max_db_date,
            format="DD/MM/YYYY",
        )

        df_filtered = df.copy()

        if selected_muscle_groups:
            df_filtered = df_filtered[
                df_filtered["Grup Muscular"].isin(selected_muscle_groups)
            ]

        if selected_exercises:
            df_filtered = df_filtered[
                df_filtered["Exercici"].isin(selected_exercises)
            ]

        if isinstance(date_range, tuple) and len(date_range) == 2:
            start_d, end_d = date_range
            df_filtered = df_filtered[
                (df_filtered["Data_Dt"] >= start_d)
                & (df_filtered["Data_Dt"] <= end_d)
            ]

        tab1, tab2 = st.tabs(
            ["🏆 Rècards i Últims Registres", "📈 Evolució de Rendiment"]
        )

        # TAB 1: PERSONAL RECORDS & RECENT WORKOUTS
        with tab1:
            if df_filtered.empty:
                st.info("No hi ha dades per als filtres seleccionats.")
            else:
                df_tab1 = df_filtered.copy()
                df_tab1["Set_Desc"] = df_tab1.apply(format_workout_set, axis=1)

                st.subheader("⏱️ Últim Entrenament per Exercici")
                st.caption(
                    "Detall de les sèries realitzades en l'últim dia d'entrenament registrat."
                )

                latest_dates = (
                    df_filtered.groupby("Exercici")["Data"].max().reset_index()
                )
                last_workout_sets = pd.merge(
                    df_tab1, latest_dates, on=["Exercici", "Data"], how="inner"
                ).sort_values(by="Data", ascending=False)

                for ex in last_workout_sets["Exercici"].unique():
                    ex_data = last_workout_sets[last_workout_sets["Exercici"] == ex]
                    mg = ex_data["Grup Muscular"].iloc[0]
                    date_str = pd.to_datetime(ex_data["Data"].iloc[0]).strftime(
                        "%d/%m/%Y"
                    )

                    with st.expander(
                        f"🏋️ **{ex}** ({mg}) — 📅 {date_str}", expanded=False
                    ):
                        for i, (_, row) in enumerate(ex_data.iterrows()):
                            st.markdown(f"**Sèrie {i+1}:** {row['Set_Desc']}")

                st.markdown("---")
                st.subheader("🏆 Dia de Màxim Rendiment per Exercici")
                st.caption(
                    "Resum del dia de màxim registre (Volum, Temps o Repeticions)."
                )

                df_tab1["Ex_Type"] = np.where(
                    (df_tab1["Temps (min)"] > 0) & (df_tab1["Set_Volume"] == 0),
                    "Timed",
                    np.where(
                        (df_tab1["Pes (kg)"] == 0)
                        & (df_tab1["Temps (min)"] == 0)
                        & (df_tab1["Repeticions"] > 0),
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

                max_idx = daily_totals.groupby("Exercici")[
                    "Max_Metric_Value"
                ].idxmax()
                max_dates = daily_totals.loc[max_idx]

                max_day_sets = pd.merge(
                    df_tab1,
                    max_dates[["Exercici", "Data"]],
                    on=["Exercici", "Data"],
                    how="inner",
                ).sort_values(by="Data", ascending=False)

                for ex in max_day_sets["Exercici"].unique():
                    ex_data = max_day_sets[max_day_sets["Exercici"] == ex]
                    mg = ex_data["Grup Muscular"].iloc[0]
                    date_str = pd.to_datetime(ex_data["Data"].iloc[0]).strftime(
                        "%d/%m/%Y"
                    )
                    ex_type = ex_data["Ex_Type"].iloc[0]

                    if ex_type == "Timed":
                        val = ex_data["Temps (min)"].sum()
                        val_str = (
                            f"{int(val)} min" if val == int(val) else f"{val:.1f} min"
                        )
                    elif ex_type == "BW_Reps":
                        val = ex_data["Repeticions"].sum()
                        val_str = f"{int(val):,} reps"
                    else:
                        val = ex_data["Set_Volume"].sum()
                        val_str = f"{val:,.0f} kg Vol"

                    with st.expander(
                        f"⭐ **{ex}** ({mg}) — 🏆 {val_str} ({date_str})",
                        expanded=False,
                    ):
                        for i, (_, row) in enumerate(ex_data.iterrows()):
                            st.markdown(f"**Sèrie {i+1}:** {row['Set_Desc']}")

        # TAB 2: PROGRESSION CHARTS & ANALYTICS
        with tab2:
            st.subheader("📈 Evolució de Rendiment i Volum")
            st.caption(
                "Passa o toca qualsevol punt per veure el desglossament de sèries d'aquell dia."
            )

            if df_filtered.empty:
                st.info("No hi ha dades disponibles per als filtres seleccionats.")
            else:
                df_tab2 = df_filtered.copy()
                df_tab2["Set_Desc"] = df_tab2.apply(format_workout_set, axis=1)

                daily_exercise_summary = (
                    df_tab2.groupby(["Data", "Exercici"])
                    .apply(
                        lambda g: pd.Series(
                            {
                                "Set_Volume": g["Set_Volume"].sum(),
                                "Max_Pes": g["Pes (kg)"].max(),
                                "Max_e1RM": g["Estimated_1RM"].max(),
                                "Set_Details_HTML": "<br>".join(
                                    [
                                        f"Sèrie {i+1}: {row['Set_Desc']}"
                                        for i, (_, row) in enumerate(g.iterrows())
                                    ]
                                ),
                            }
                        )
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
                        x=0.5,
                    ),
                    hovermode="closest",
                    font=dict(size=11),
                )

                # CHART 1: DAILY VOLUME
                fig_vol = px.line(
                    daily_exercise_summary,
                    x="Data",
                    y="Set_Volume",
                    color="Exercici",
                    title="📦 Volum Total Diari (kg)",
                    markers=True,
                    custom_data=["Set_Details_HTML", "Exercici"],
                )

                fig_vol.update_traces(
                    hovertemplate=(
                        "<b>%{customdata[1]}</b><br>"
                        + "📅 %{x|%d/%m/%Y}<br>"
                        + "📦 Volum Total: %{y:,.0f} kg<br>"
                        + "--------------------<br>"
                        + "%{customdata[0]}<extra></extra>"
                    )
                )

                fig_vol.update_layout(**mobile_layout_defaults)
                fig_vol.update_xaxes(title_text="", showgrid=True)
                fig_vol.update_yaxes(title_text="kg")

                st.plotly_chart(
                    fig_vol, use_container_width=True, config={"displayModeBar": False}
                )

                st.markdown("---")

                # CHART 2: STRENGTH METRIC
                metric_choice = st.radio(
                    "Mètrica de Força:",
                    options=["e1RM Estimat", "Pes Màxim Aixecat"],
                    horizontal=True,
                    key="metric_choice_tab2",
                )

                y_col = "Max_e1RM" if metric_choice == "e1RM Estimat" else "Max_Pes"
                y_label = (
                    "e1RM Estimat"
                    if metric_choice == "e1RM Estimat"
                    else "Pes Màxim"
                )

                fig_strength = px.line(
                    daily_exercise_summary,
                    x="Data",
                    y=y_col,
                    color="Exercici",
                    title=f"💪 Evolució de Força ({y_label})",
                    markers=True,
                    custom_data=["Set_Details_HTML", "Exercici"],
                )

                fig_strength.update_traces(
                    hovertemplate=(
                        "<b>%{customdata[1]}</b><br>"
                        + "📅 %{x|%d/%m/%Y}<br>"
                        + f"💪 {y_label}: %{{y:.1f}} kg<br>"
                        + "--------------------<br>"
                        + "%{customdata[0]}<extra></extra>"
                    )
                )

                fig_strength.update_layout(**mobile_layout_defaults)
                fig_strength.update_xaxes(title_text="", showgrid=True)
                fig_strength.update_yaxes(title_text="kg")

                st.plotly_chart(
                    fig_strength,
                    use_container_width=True,
                    config={"displayModeBar": False},
                )

                st.markdown("---")

                # CHART 3: TOTAL SETS BY MUSCLE GROUP
                muscle_summary = (
                    df_filtered.groupby("Grup Muscular")
                    .agg(
                        Total_Series=("Set_Volume", "count"),
                        Total_Reps=("Repeticions", "sum"),
                    )
                    .reset_index()
                )

                fig_muscle = px.bar(
                    muscle_summary,
                    x="Grup Muscular",
                    y="Total_Series",
                    text="Total_Series",
                    title="📊 Total de Sèries per Grup Muscular",
                    labels={
                        "Total_Series": "Nº de Sèries",
                        "Grup Muscular": "Grup",
                    },
                )
                fig_muscle.update_traces(textposition="outside")
                fig_muscle.update_layout(
                    margin=dict(l=10, r=10, t=40, b=40), font=dict(size=11)
                )
                fig_muscle.update_xaxes(title_text="")
                fig_muscle.update_yaxes(title_text="Sèries")

                st.plotly_chart(
                    fig_muscle,
                    use_container_width=True,
                    config={"displayModeBar": False},
                )