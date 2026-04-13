from io import BytesIO

import pandas as pd
import streamlit as st

try:
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False


st.set_page_config(
    page_title="Data Comparison Agent",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

MAX_FILES = 4
DIFF_COLOR = "FFEB9C"
MISSING_COLOR = "FFC7CE"
SAME_COLOR = "C6EFCE"
HEADER_COLOR = "4472C4"


if "file_slots" not in st.session_state:
    st.session_state.file_slots = 2


def add_slot():
    if st.session_state.file_slots < MAX_FILES:
        st.session_state.file_slots += 1


def remove_slot():
    if st.session_state.file_slots > 2:
        st.session_state.file_slots -= 1


def load_file(uploaded_file):
    if uploaded_file is None:
        return None
    name = uploaded_file.name.lower()
    try:
        if name.endswith(".csv"):
            return pd.read_csv(uploaded_file)
        if name.endswith((".xlsx", ".xls")):
            return pd.read_excel(uploaded_file)
        if name.endswith(".xml"):
            return pd.read_xml(uploaded_file)
    except Exception as exc:
        st.error(f"'{uploaded_file.name}' dosyası okunamadı: {exc}")
    return None


def ensure_unique(name, existing):
    if name not in existing:
        return name
    n = 2
    while f"{name} ({n})" in existing:
        n += 1
    return f"{name} ({n})"


def build_column_matrix(dfs_with_names):
    all_cols = []
    for _, df in dfs_with_names:
        for c in df.columns:
            if c not in all_cols:
                all_cols.append(c)
    rows = []
    for col in all_cols:
        row = {"Kolon adı": col}
        present = 0
        for name, df in dfs_with_names:
            if col in df.columns:
                row[name] = "✓ Var"
                present += 1
            else:
                row[name] = "✗ Yok"
        row["Durum"] = (
            "Tüm dosyalarda var"
            if present == len(dfs_with_names)
            else "Bazı dosyalarda yok"
        )
        rows.append(row)
    return pd.DataFrame(rows)


def build_wide_comparison(dfs_with_names, key_col):
    file_names = [name for name, _ in dfs_with_names]

    all_cols = []
    for _, df in dfs_with_names:
        for c in df.columns:
            if c != key_col and c not in all_cols:
                all_cols.append(c)

    indexed = {}
    for name, df in dfs_with_names:
        d = df.copy()
        d[key_col] = d[key_col].astype(str)
        d = d.drop_duplicates(subset=[key_col]).set_index(key_col)
        indexed[name] = d

    all_keys = set()
    for d in indexed.values():
        all_keys.update(d.index.tolist())
    all_keys = sorted(all_keys)

    value_rows = []
    status_rows = []

    for k in all_keys:
        v_row = {"Satır anahtarı": k}
        s_row = {"Satır anahtarı": ""}
        row_has_diff = False
        row_has_missing = False

        for col in all_cols:
            cell_values = []
            for name in file_names:
                d = indexed[name]
                if col in d.columns and k in d.index:
                    v = d.at[k, col]
                    if pd.isna(v):
                        cell_values.append(None)
                    else:
                        cell_values.append(v)
                else:
                    cell_values.append(None)

            non_null_str = [str(v) for v in cell_values if v is not None]
            col_is_diff = len(set(non_null_str)) > 1 if non_null_str else False
            col_has_missing = any(v is None for v in cell_values)

            if col_is_diff:
                row_has_diff = True
            if col_has_missing:
                row_has_missing = True

            for i, name in enumerate(file_names):
                label = f"{col} — {name}"
                v_row[label] = "" if cell_values[i] is None else cell_values[i]
                if cell_values[i] is None:
                    s_row[label] = "missing"
                elif col_is_diff:
                    s_row[label] = "diff"
                else:
                    s_row[label] = "same"

        if row_has_diff:
            v_row["Durum"] = "Farklılık var"
            s_row["Durum"] = "diff"
        elif row_has_missing:
            v_row["Durum"] = "Bazı dosyalarda yok"
            s_row["Durum"] = "missing"
        else:
            v_row["Durum"] = "Tamamen aynı"
            s_row["Durum"] = "same"

        value_rows.append(v_row)
        status_rows.append(s_row)

    values_df = pd.DataFrame(value_rows)
    status_df = pd.DataFrame(status_rows)

    summary = {
        "total_keys": len(all_keys),
        "identical": int((values_df["Durum"] == "Tamamen aynı").sum()) if not values_df.empty else 0,
        "with_diff": int((values_df["Durum"] == "Farklılık var").sum()) if not values_df.empty else 0,
        "missing": int((values_df["Durum"] == "Bazı dosyalarda yok").sum()) if not values_df.empty else 0,
    }

    return values_df, status_df, summary


def style_wide(values_df, status_df):
    v = values_df.reset_index(drop=True)
    s = status_df.reset_index(drop=True)

    def apply_styles(df):
        styles = pd.DataFrame("", index=df.index, columns=df.columns)
        for col in df.columns:
            if col not in s.columns:
                continue
            for ri in df.index:
                status = s.at[ri, col]
                if status == "diff":
                    styles.at[ri, col] = f"background-color: #{DIFF_COLOR}"
                elif status == "missing":
                    styles.at[ri, col] = f"background-color: #{MISSING_COLOR}"
                elif status == "same" and col == "Durum":
                    styles.at[ri, col] = f"background-color: #{SAME_COLOR}"
        return styles

    return v.style.apply(apply_styles, axis=None)


def style_column_matrix(col_matrix_df):
    def apply_styles(df):
        styles = pd.DataFrame("", index=df.index, columns=df.columns)
        for ri in df.index:
            durum = df.at[ri, "Durum"]
            if durum == "Bazı dosyalarda yok":
                styles.at[ri, "Durum"] = f"background-color: #{MISSING_COLOR}"
            elif durum == "Tüm dosyalarda var":
                styles.at[ri, "Durum"] = f"background-color: #{SAME_COLOR}"
            for col in df.columns:
                if col in ("Kolon adı", "Durum"):
                    continue
                if df.at[ri, col] == "✗ Yok":
                    styles.at[ri, col] = f"background-color: #{MISSING_COLOR}"
        return styles

    return col_matrix_df.style.apply(apply_styles, axis=None)


def _style_workbook(wb, values_df, status_df, col_matrix_df):
    header_fill = PatternFill("solid", fgColor=HEADER_COLOR)
    header_font = Font(bold=True, color="FFFFFF", size=11)
    diff_fill = PatternFill("solid", fgColor=DIFF_COLOR)
    missing_fill = PatternFill("solid", fgColor=MISSING_COLOR)
    same_fill = PatternFill("solid", fgColor=SAME_COLOR)
    border = Border(
        left=Side(style="thin", color="DDDDDD"),
        right=Side(style="thin", color="DDDDDD"),
        top=Side(style="thin", color="DDDDDD"),
        bottom=Side(style="thin", color="DDDDDD"),
    )

    for sheet in wb.sheetnames:
        ws = wb[sheet]
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = border
        for col_idx, col_cells in enumerate(ws.columns, start=1):
            max_len = 14
            for cell in col_cells:
                if cell.value is not None:
                    max_len = max(max_len, min(len(str(cell.value)) + 2, 45))
            ws.column_dimensions[get_column_letter(col_idx)].width = max_len
        ws.row_dimensions[1].height = 28

    def paint_from_status(ws, value_df, status_subset):
        col_headers = [c.value for c in ws[1]]
        for row_idx in range(len(value_df)):
            for c_idx, col_name in enumerate(col_headers, start=1):
                if col_name not in status_subset.columns:
                    continue
                status = status_subset.iloc[row_idx][col_name]
                cell = ws.cell(row=row_idx + 2, column=c_idx)
                if col_name == "Durum":
                    if status == "diff":
                        cell.fill = diff_fill
                    elif status == "missing":
                        cell.fill = missing_fill
                    elif status == "same":
                        cell.fill = same_fill
                else:
                    if status == "diff":
                        cell.fill = diff_fill
                    elif status == "missing":
                        cell.fill = missing_fill

    if "Tum Satirlar" in wb.sheetnames:
        paint_from_status(wb["Tum Satirlar"], values_df, status_df)
        wb["Tum Satirlar"].freeze_panes = "B2"

    if "Sadece Farkliliklar" in wb.sheetnames:
        diff_mask = values_df["Durum"] != "Tamamen aynı"
        diff_values = values_df[diff_mask].reset_index(drop=True)
        diff_status = status_df[diff_mask].reset_index(drop=True)
        paint_from_status(wb["Sadece Farkliliklar"], diff_values, diff_status)
        wb["Sadece Farkliliklar"].freeze_panes = "B2"

    if "Kolon Karsilastirmasi" in wb.sheetnames:
        ws = wb["Kolon Karsilastirmasi"]
        headers = [c.value for c in ws[1]]
        for row in ws.iter_rows(min_row=2):
            for idx, col_name in enumerate(headers):
                cell = row[idx]
                if col_name == "Durum":
                    if cell.value == "Bazı dosyalarda yok":
                        cell.fill = missing_fill
                    elif cell.value == "Tüm dosyalarda var":
                        cell.fill = same_fill
                elif col_name not in ("Kolon adı",):
                    if cell.value == "✗ Yok":
                        cell.fill = missing_fill


def build_excel(dfs_with_names, col_matrix_df, values_df, status_df, summary):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        ozet = pd.DataFrame(
            [
                ["Yüklenen dosya sayısı", len(dfs_with_names)],
                ["Toplam benzersiz satır sayısı", summary["total_keys"]],
                ["Tüm dosyalarda aynı olan satırlar", summary["identical"]],
                ["Farklılık içeren satırlar", summary["with_diff"]],
                ["Bazı dosyalarda olmayan satırlar", summary["missing"]],
                ["", ""],
                ["Renk açıklaması", ""],
                ["Sarı", "Aynı satırın değeri dosyalar arasında farklı"],
                ["Kırmızı", "Değer bazı dosyalarda yok"],
                ["Yeşil", "Tüm dosyalarda aynı"],
            ],
            columns=["Açıklama", "Değer"],
        )
        ozet.to_excel(writer, sheet_name="Ozet", index=False)

        col_matrix_df.to_excel(writer, sheet_name="Kolon Karsilastirmasi", index=False)
        values_df.to_excel(writer, sheet_name="Tum Satirlar", index=False)

        only_diffs = values_df[values_df["Durum"] != "Tamamen aynı"].reset_index(drop=True)
        only_diffs.to_excel(writer, sheet_name="Sadece Farkliliklar", index=False)

        if HAS_OPENPYXL:
            _style_workbook(writer.book, values_df, status_df, col_matrix_df)

    output.seek(0)
    return output.getvalue()


st.title("Data Comparison Agent")

st.markdown(
    """
    Bu araç, yüklediğiniz **2 ila 4 dosya** arasındaki farkları size net bir şekilde gösterir.
    Dosyalarınız üzerinde **hiçbir değişiklik yapılmaz**; araç sadece farklılıkları tespit eder ve görsel olarak işaretler.
    """
)

with st.expander("Nasıl kullanılır?", expanded=False):
    st.markdown(
        """
        1. Karşılaştırmak istediğiniz dosyaları yükleyin (Excel, CSV veya XML formatında).
        2. İsterseniz alttaki **➕ Karşılaştırmaya bir dosya daha ekle** butonuyla en fazla 4 dosyaya kadar ekleyebilirsiniz.
        3. Satırların hangi kolona göre eşleştirileceğini seçin. Bu kolon, her satırı benzersiz şekilde tanımlayan bir alan olmalıdır (örneğin *müşteri numarası*, *sipariş no*, *ürün kodu* gibi).
        4. **Karşılaştırmayı başlat** butonuna basın.
        5. Sonuçları ekranda görebilir veya renk kodlu Excel dosyası olarak indirebilirsiniz.

        **Renklerin anlamı**
        - 🟡 **Sarı:** Aynı satırın değeri dosyalar arasında farklı
        - 🔴 **Kırmızı:** Değer bazı dosyalarda bulunmuyor
        - 🟢 **Yeşil:** Tüm dosyalarda aynı
        """
    )

st.divider()

st.header("1. Dosyalarınızı yükleyin")
st.caption("En az 2, en fazla 4 dosya yükleyebilirsiniz. Desteklenen formatlar: .csv, .xlsx, .xls, .xml")

uploaded_files = []
num_slots = st.session_state.file_slots
idx = 0
while idx < num_slots:
    row_cols = st.columns(2)
    for rc in row_cols:
        if idx >= num_slots:
            break
        with rc:
            f = st.file_uploader(
                f"Dosya {idx + 1}",
                type=["csv", "xlsx", "xls", "xml"],
                key=f"upload_{idx}",
            )
            if f is not None:
                uploaded_files.append(f)
        idx += 1

btn_cols = st.columns([2, 2, 3])
with btn_cols[0]:
    st.button(
        "➕ Karşılaştırmaya bir dosya daha ekle",
        on_click=add_slot,
        disabled=num_slots >= MAX_FILES,
        use_container_width=True,
    )
with btn_cols[1]:
    st.button(
        "➖ Son alanı kaldır",
        on_click=remove_slot,
        disabled=num_slots <= 2,
        use_container_width=True,
    )

dfs_with_names = []
for file in uploaded_files:
    df = load_file(file)
    if df is not None:
        existing_names = [n for n, _ in dfs_with_names]
        unique_name = ensure_unique(file.name, existing_names)
        dfs_with_names.append((unique_name, df))

if len(dfs_with_names) < 2:
    st.info("Karşılaştırma için en az 2 dosya yüklemeniz gerekir.")
    st.stop()

st.success(f"✅ {len(dfs_with_names)} dosya başarıyla yüklendi.")

st.divider()

st.header("2. Yüklediğiniz dosyalara göz atın")
st.caption("Aşağıdaki sekmelerden her dosyanın içeriğini kontrol edebilirsiniz.")

preview_tabs = st.tabs([name for name, _ in dfs_with_names])
for tab, (name, df) in zip(preview_tabs, dfs_with_names):
    with tab:
        mc1, mc2 = st.columns(2)
        mc1.metric("Satır sayısı", df.shape[0])
        mc2.metric("Kolon sayısı", df.shape[1])
        st.dataframe(df, use_container_width=True, hide_index=True)

st.divider()

st.header("3. Satırları hangi kolona göre eşleştirelim?")
st.markdown(
    "Sistemin doğru çalışabilmesi için **her satırı benzersiz şekilde tanımlayan** "
    "bir kolon seçmeniz gerekiyor. Örneğin: *müşteri numarası*, *sipariş no*, "
    "*ürün kodu* veya *id* gibi bir alan."
)

common_columns = set(dfs_with_names[0][1].columns)
for _, df in dfs_with_names[1:]:
    common_columns &= set(df.columns)
common_columns = sorted(common_columns)

if not common_columns:
    st.error(
        "❌ Yüklediğiniz dosyalarda **ortak bir kolon bulunamadı**. "
        "Satırları eşleştirebilmek için tüm dosyalarda en az bir ortak kolon olması gerekir. "
        "Aşağıda dosyalardaki tüm kolonların listesini görebilirsiniz:"
    )
    col_matrix_df = build_column_matrix(dfs_with_names)
    st.dataframe(
        style_column_matrix(col_matrix_df),
        use_container_width=True,
        hide_index=True,
    )
    st.stop()

key_col = st.selectbox(
    "Eşleştirme kolonu",
    common_columns,
    help="Bu listede tüm dosyalarda ortak olan kolonlar görünür.",
)

start = st.button(
    "🔍 Karşılaştırmayı başlat",
    type="primary",
    use_container_width=True,
)

if not start:
    st.stop()

with st.spinner("Dosyalarınız karşılaştırılıyor, lütfen bekleyin..."):
    col_matrix_df = build_column_matrix(dfs_with_names)
    values_df, status_df, summary = build_wide_comparison(dfs_with_names, key_col)

st.divider()
st.header("4. Sonuçlar")

m1, m2, m3, m4 = st.columns(4)
m1.metric("Toplam satır", summary["total_keys"])
m2.metric("Tamamen aynı", summary["identical"])
m3.metric("Farklılık içeren", summary["with_diff"])
m4.metric("Bazı dosyalarda yok", summary["missing"])

st.markdown(
    f"""
    <div style="margin-top: 12px;">
    <span style="background-color:#{DIFF_COLOR};padding:4px 10px;border-radius:4px;margin-right:8px;">🟡 Farklılık</span>
    <span style="background-color:#{MISSING_COLOR};padding:4px 10px;border-radius:4px;margin-right:8px;">🔴 Eksik</span>
    <span style="background-color:#{SAME_COLOR};padding:4px 10px;border-radius:4px;">🟢 Aynı</span>
    </div>
    """,
    unsafe_allow_html=True,
)

tab_rows, tab_cols, tab_excel = st.tabs(
    ["Tüm Satırlar (Yan Yana)", "Kolon Karşılaştırması", "Excel İndir"]
)

with tab_rows:
    st.markdown(
        "Aşağıda yüklediğiniz **tüm satırlar** gösteriliyor. Her satır için, "
        "aynı anahtarın **farklı dosyalardaki karşılıkları yan yana** listelenmiştir. "
        "Farklı olan değerler **sarı**, bazı dosyalarda bulunmayan değerler **kırmızı** ile işaretlenmiştir."
    )
    filter_choice = st.radio(
        "Filtrele:",
        [
            "Tümünü göster",
            "Sadece farklılık içerenler",
            "Sadece bazı dosyalarda olmayanlar",
            "Sadece tamamen aynı olanlar",
        ],
        horizontal=True,
    )
    mask = pd.Series(True, index=values_df.index)
    if filter_choice == "Sadece farklılık içerenler":
        mask = values_df["Durum"] == "Farklılık var"
    elif filter_choice == "Sadece bazı dosyalarda olmayanlar":
        mask = values_df["Durum"] == "Bazı dosyalarda yok"
    elif filter_choice == "Sadece tamamen aynı olanlar":
        mask = values_df["Durum"] == "Tamamen aynı"

    display_values = values_df[mask].reset_index(drop=True)
    display_status = status_df[mask].reset_index(drop=True)

    if display_values.empty:
        st.info("Bu filtreye uyan satır bulunamadı.")
    else:
        st.dataframe(
            style_wide(display_values, display_status),
            use_container_width=True,
            hide_index=True,
        )

with tab_cols:
    st.markdown(
        "Her kolonun hangi dosyalarda bulunduğunu aşağıdan görebilirsiniz. "
        "**✓ Var** = kolon o dosyada mevcut, **✗ Yok** = kolon o dosyada bulunmuyor."
    )
    st.dataframe(
        style_column_matrix(col_matrix_df),
        use_container_width=True,
        hide_index=True,
    )

with tab_excel:
    st.markdown(
        "Karşılaştırma sonucunu **renk kodlu bir Excel dosyası** olarak indirebilirsiniz. "
        "İndirdiğiniz dosyada farklılıklar **sarı**, eksik değerler **kırmızı**, "
        "aynı olanlar **yeşil** ile işaretlenmiştir."
    )
    st.markdown(
        "**Excel dosyasında 4 sayfa bulunacak:**\n"
        "- **Özet:** Genel bir özet ve renk açıklamaları\n"
        "- **Kolon Karşılaştırması:** Hangi kolonun hangi dosyada olduğu\n"
        "- **Tüm Satırlar:** Tüm satırlar, yan yana tüm dosyalardaki değerler\n"
        "- **Sadece Farklılıklar:** Yalnızca farklılık veya eksik içeren satırlar"
    )
    excel_bytes = build_excel(
        dfs_with_names, col_matrix_df, values_df, status_df, summary
    )
    st.download_button(
        "📥 Excel dosyasını indir",
        data=excel_bytes,
        file_name="karsilastirma_sonucu.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
